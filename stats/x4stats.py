import xml.etree.ElementTree as ET
import gzip
import pandas as pd
import numpy as np
import math


class X4stats:

    def __init__(self, save):

        with gzip.open(save) as f:
            self.xmltree = ET.parse(f).getroot()

            # Find all player owned ships and stations
            self.game_time = self.__calc_game_time()
            # print("Game time", str(int(self.game_time) / 3600) + ' hours')
            # pd.set_option('display.max_rows', None)
            self.own_ships, self.own_ship_ids = self.__calc_ship_info()
            self.sales = self.__calc_sales()

            # get rid of large xml in memory
            self.xmltree = None

    def get_game_time(self):
        return self.game_time

    def __calc_game_time(self):
        for elem in self.xmltree.findall("./info/game"):
            # print(elem.attrib["time"])
            return float(elem.attrib["time"])

    def get_df_sales(self, hours=None):
        df = self.sales.copy()
        print(df)
        if hours:
            df = df.query("hours_since_event <= " + str(hours))
        print(df)
        return df

    def get_df_per_ship(self, hours=None):
        return self.calc_df_per_ship(hours)

    def calc_df_per_ship(self, hours=None):
        df = self.get_df_sales(hours)
        df_per_ship = df.drop(["time", "ware", "hours_since_event"], axis=1) \
            .groupby(["ship_id", "ship_class", "commander_name", "ship_code", "ship_name", "ship_type"]
                     , dropna=False).sum().reset_index()
        # print(df_per_ship.head())

        df_per_ship.columns = ["ship_id", "ship_class", "commander_name", "ship_code", "ship_name", "ship_type"
            , "value", "sales", "costs", "volume"]
        df_per_ship["margin"] = (df_per_ship["sales"] - df_per_ship["costs"]) / df_per_ship["sales"]
        df_per_ship.loc[df_per_ship.margin < -1, 'margin'] = -1
        df_per_ship["margin"].replace([-np.inf, np.nan], 0, inplace=True)
        # print("per ship\n", df_per_ship.head())
        return df_per_ship

    # Loop through all trade transactions to collect transactions where the player is seller or buyer
    def __calc_sales(self):
        sales_list = []
        for elem in self.xmltree.findall("./economylog/entries[@type='trade']/log[@seller]"):

            try:
                if elem.attrib["seller"] in self.own_ship_ids:
                    if "price" in elem.attrib:
                        value = elem.attrib["price"]
                        sales = elem.attrib["price"]
                    else:
                        value = None
                        sales = None
                    sale = {
                        "time": elem.attrib["time"],
                        "ship_id": elem.attrib["seller"],
                        "value": value,
                        "sales": sales,
                        "costs": 0,
                        "volume": elem.attrib["v"],
                        "ware": elem.attrib["ware"],
                    }
                    sales_list = self.append_sales_list(sales_list, sale)

                if "buyer" in elem.attrib and elem.attrib["buyer"] in self.own_ship_ids:
                    if "price" in elem.attrib:
                        value = -1 * float(elem.attrib["price"])
                        costs = elem.attrib["price"]
                    else:
                        value = None
                        costs = None
                    sale = {
                        "time": elem.attrib["time"],
                        "ship_id": elem.attrib["buyer"],
                        "value": value,
                        "sales": 0,
                        "costs": costs,
                        "volume": elem.attrib["v"],
                        "ware": elem.attrib["ware"],
                    }
                    sales_list = self.append_sales_list(sales_list, sale)

            except KeyError as e:
                print(str(type(e)))
                print(elem.attrib)
                raise

        df = pd.DataFrame(sales_list)
        # convert certain columns to float
        df["time"] = df["time"].astype(float)
        df["value"] = df["value"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df["sales"] = df["sales"].astype(float)
        df["costs"] = df["costs"].astype(float)

        # hour passed since event
        df["hours_since_event"] = df["time"].apply(self.hours_passed)

        # display updated DataFrame
        # print(df)
        # print("sales\n", df.head())
        return df

    # append sales record to sale list
    def append_sales_list(self, sales_list, sale):

        atts = self.get_id_attributes(sale["ship_id"])
        sales_list.append({
            "ship_id": sale["ship_id"],
            "ship_type": atts["type"],
            "ship_class": atts["class"],
            "ship_name": atts["name"],
            "ship_code": atts["code"],
            "commander_name": atts["commander_name"],
            "time": sale["time"],
            "ware": sale["ware"],
            "value": sale["value"],
            "sales": sale["sales"],
            "costs": sale["costs"],
            "volume": sale["volume"],
        })
        # print(atts["code"], atts["name"], sale["transaction"])
        return sales_list

    # Return tuple with players ship/station info and ids
    def __calc_ship_info(self):
        info = []
        ids = []

        for elem in self.xmltree.findall("./universe/component/connections//component[@owner='player']"):
            if "class" in elem.attrib and elem.attrib["class"] in ("ship_m"
                                                                        , "ship_s"
                                                                        , "ship_l"
                                                                        , "ship_xl"
                                                                        , "station"):
                try:
                    ship_type = None
                    ship_id = None
                    code = None
                    subordinates_cons = []
                    commander_cons = []
                    commander_id = None
                    commander_name = None
                    ship_class = elem.attrib["class"]

                    if "macro" in elem.attrib:
                        ship_type = elem.attrib["macro"]
                    if "id" in elem.attrib:
                        ship_id = elem.attrib["id"]
                    if "code" in elem.attrib:
                        code = elem.attrib["code"]
                    if "name" in elem.attrib:
                        name = elem.attrib["name"]
                    else:
                        name = code

                    if ship_class == 'station':
                        # subordinate connections zoeken voor stations
                        for sub_con in elem.findall(".//connection[@connection='subordinates']"):
                            subordinates_cons.append(sub_con.attrib["id"])

                    # commander connections zoeken voor schepen
                    if ship_class != 'station':
                        for com_con in elem.findall(".//connection[@connection='commander']/connected"):
                            commander_cons.append(com_con.attrib["connection"])

                    info.append({
                        "type": ship_type,
                        "id": ship_id,
                        "name": name,
                        "code": code,
                        "subordinate_cons": subordinates_cons,
                        "commander_cons": commander_cons,
                        "class": ship_class,
                        "commander_id": commander_id,
                        "commander_name": commander_name,
                    })
                    ids.append(ship_id)
                except KeyError as e:
                    print(str(e))
                    print(elem.attrib)

        # stations aan schepen verbinden
        for e in info:
            # schip heeft 1 commander
            if len(e["commander_cons"]) == 1:
                # zoek commander id
                for c in info:
                    if e["commander_cons"][0] in c["subordinate_cons"]:
                        e["commander_id"] = c["id"]
                        e["commander_name"] = c["name"]
            else:
                # Bij geen commander ben je eigen baas tbv groepering per commander
                e["commander_id"] = e["id"]
                e["commander_name"] = e["name"]

        # for i in info:
        #     print(i)
        return info, ids

    def get_id_attributes(self, ship_id):
        for c in self.own_ships:
            if c["id"] == ship_id:
                return c
        return None

    def hours_passed(self, time):
        return math.floor((self.game_time - time) / 3600)

    def get_profit(self, df):
        return df["value"].sum()

