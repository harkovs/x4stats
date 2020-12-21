import xml.etree.ElementTree as ET
import gzip
import pandas as pd
import numpy as np
import math
from pathlib import Path
import os
import time
import shutil

# trade or mining orders
ECO_ORDERS = [
    'MiningRoutine_Basic'
    , 'MiningRoutine'
    , 'MiningRoutine_Advanced'
    , 'MiddleMan'
    , 'TradeRoutine'
    , 'TradeRouttine_Basic'
    , 'TradeRouttine_Advanced'
    , 'FindBuildTasks'
    ]
SHIP_CLASSES = [
    'ship_s'
    , 'ship_m'
    , 'ship_l'
    , 'ship_xl'
    , 'ship_s'
    , 'ship_s'
]

STATION_CLASSES = ['station']
PLAYER_CLASSES = ['player']
ALL_CLASSES = SHIP_CLASSES + STATION_CLASSES + PLAYER_CLASSES


class X4stats:

    def __init__(self, save_location):

        self.is_ready = False
        self.xmltree = None
        self.game_time = None
        self.own_ships = None
        self.own_ship_ids = None
        self.player_id = None
        self.sales = None
        self.save_location = save_location
        self.save_mtime = None
        self.check_for_new_file()
        # print(self.player_id)

    def check_for_new_file(self):
        # dir of file
        p = Path(self.save_location)
        if p.is_dir():
            paths = sorted(p.iterdir(), key=os.path.getmtime, reverse=True)

            i = 0
            p = None
            while i < len(paths) and not p:
                if paths[i].suffix.lower() == '.gz':
                    p = paths[i]
                i = i + 1

        mtime = os.path.getmtime(p)
        # (New) file found. Give is 10 seconds to write
        if not self.save_mtime or (self.save_mtime < mtime and (time.time() - mtime) > 10):
            self.save_mtime = mtime
            # copy to minimize interruption for the game
            p_to = Path('stats/saves/savegame_wrk.gz')
            shutil.copy(p, p_to)
            # trigger reload
            print(" * New save loading: " + str(p))
            self.reload(p_to)

    # (re)load save file
    def reload(self, save):
        with gzip.open(save) as f:
            self.xmltree = ET.parse(f).getroot()
            self.game_time = self.__calc_game_time()
            pd.set_option('display.max_rows', None)
            # Find all player owned ships and stations
            self.own_ships, self.own_ship_ids, self.player_id = self.__calc_ship_info()
            self.sales = self.__calc_sales()
            # print(self.sales.loc[self.sales["ship_name"] == 'TD Deimos'])

            # get rid of large xml in memory
            self.xmltree = None
            print(" * Loading complete")

    def get_game_time(self):
        return self.game_time

    def __calc_game_time(self):
        for elem in self.xmltree.findall("./info/game"):
            # print(elem.attrib["time"])
            return float(elem.attrib["time"])

    def get_df_sales(self, hours=None, filter_zero_value=False):
        df = self.sales.copy()
        if hours:
            # uren beginnen te tellen bij 0. Laatste 1 uur is dus uur <= 0
            hours = int(hours) - 1
            df = df.query("hours_since_event <= " + str(hours))
        if filter_zero_value:
            df = df.query("value != 0")

        return df

    def get_df_sales_sorted(self, hours=None, filter_zero_value=False):
        df = self.get_df_sales(hours, filter_zero_value)
        df = df.sort_values(["ship_name", "time"])
        return df

    def get_df_per_ship(self, hours=None):
        return self.__calc_df_per_ship(hours)

    def __calc_df_per_ship(self, hours=None):
        df = self.get_df_sales(hours)
        df_per_ship = df.drop(["time", "ware", "hours_since_event"], axis=1) \
            .groupby(["ship_id", "ship_class", "commander_name", "default_order", "ship_code", "ship_name", "ship_type"]
                     , dropna=False).sum().reset_index()
        # print(df_per_ship.head())

        df_per_ship.columns = ["ship_id", "ship_class", "commander_name", "default_order", "ship_code", "ship_name"
            , "ship_type", "value", "sales", "costs", "volume"]

        df_per_ship = self.__per_x_help(df_per_ship)

        return df_per_ship

    # geen trade waarde in de laatste X uren, maar wel trade orders
    def get_idle_traders_miners(self, hours):
        df = self.__calc_df_per_ship(hours)
        return df.loc[
            (df['default_order'].isin(ECO_ORDERS))
            & (df['ship_class'].isin(SHIP_CLASSES))
            & (df['value'] == 0)
        ]

    # df['ship_class'].isin(SHIP_CLASSES), df['value'] == 0

    def get_df_per_commander(self, hours=None):
        return self.__calc_df_per_commander(hours)

    def __calc_df_per_commander(self, hours=None):
        df = self.get_df_sales(hours)
        df_per_com = df.drop(["time", "ware", "hours_since_event"], axis=1) \
            .groupby(["commander_name"]
                     , dropna=False).sum().reset_index()
        # print(df_per_com.head())

        df_per_com.columns = ["commander_name", "value", "sales", "costs", "volume"]
        df_per_com = self.__per_x_help(df_per_com)
        # print(df_per_com)
        return df_per_com

    # Margekolom en afronding
    @staticmethod
    def __per_x_help(df_perx):
        df_perx["margin"] = (df_perx["sales"] - df_perx["costs"]) / df_perx["sales"]
        df_perx.loc[df_perx.margin < -1, 'margin'] = -1
        df_perx["margin"].replace([-np.inf, np.nan], 0, inplace=True)

        # afronden
        cols = ["value", "sales", "costs", "volume", "margin"]
        df_perx[cols] = df_perx[cols].round({"value": 0, "sales": 0, "costs": 0, "volume": 0, "margin": 4})

        return df_perx

    # Loop through all trade transactions to collect transactions where the player is seller or buyer
    def __calc_sales(self):
        sales_list = []
        for elem in self.xmltree.findall("./economylog/entries[@type='trade']/log[@seller]"):

            try:
                if elem.attrib["seller"] in self.own_ship_ids and "price" in elem.attrib:
                    volume = float(elem.attrib["v"])
                    # prijs is in centen
                    value = volume * float(elem.attrib["price"]) / 100
                    sales = volume * float(elem.attrib["price"]) / 100
                    sale = {
                        "time": elem.attrib["time"],
                        "ship_id": elem.attrib["seller"],
                        "value": value,
                        "sales": sales,
                        "costs": 0,
                        "volume": volume,
                        "ware": elem.attrib["ware"],
                    }
                    sales_list = self.__append_sales_list(sales_list, sale)

                if "buyer" in elem.attrib and elem.attrib["buyer"] in self.own_ship_ids and "price" in elem.attrib:
                    volume = float(elem.attrib["v"])
                    value = -1 * volume * float(elem.attrib["price"]) / 100
                    costs = volume * float(elem.attrib["price"]) / 100
                    sale = {
                        "time": elem.attrib["time"],
                        "ship_id": elem.attrib["buyer"],
                        "value": value,
                        "sales": 0,
                        "costs": costs,
                        "volume": volume,
                        "ware": elem.attrib["ware"],
                    }
                    sales_list = self.__append_sales_list(sales_list, sale)

            except KeyError as e:
                print(str(type(e)))
                print(elem.attrib)
                raise

        # Add ships with trade/mine orders and stations to make sure they are displayed even without trade value.
        for ship in self.own_ships:
            if ship["class"] in (SHIP_CLASSES + PLAYER_CLASSES) or ship["default_order"]:
                sale = {
                    "time": self.game_time,
                    "ship_id": ship["id"],
                    "value": 0,
                    "sales": 0,
                    "costs": 0,
                    "volume": 0,
                    "ware": None,
                }
                sales_list = self.__append_sales_list(sales_list, sale)

        # transfers van station accounts
        account_mutations = self.__calc_account_mutations()
        for m in account_mutations:
            sales_list = self.__append_sales_list(sales_list, m)

        df = pd.DataFrame(sales_list)
        # convert certain columns to float
        try:
            df["time"] = df["time"].astype(float)
            df["value"] = df["value"].astype(float)
            df["volume"] = df["volume"].astype(float)
            df["sales"] = df["sales"].astype(float)
            df["costs"] = df["costs"].astype(float)
        except KeyError as e:
            print(str(e))
            print('No records found. Is the game version at 4.00 or higher?')
            raise
        # hour passed since event
        df["hours_since_event"] = df["time"].apply(self.hours_passed)

        # display updated DataFrame
        # print(df)
        # print("sales\n", df.head())
        return df

    # append sales record to sale list
    def __append_sales_list(self, sales_list, sale):

        atts = self.get_id_attributes(sale["ship_id"])
        sales_list.append({
            "ship_id": sale["ship_id"],
            "ship_type": atts["type"],
            "ship_class": atts["class"],
            "ship_name": atts["name"],
            "ship_code": atts["code"],
            "commander_name": atts["commander_name"],
            "default_order": atts["default_order"],
            "time": sale["time"],
            "ware": sale["ware"],
            "value": sale["value"],
            "sales": sale["sales"],
            "costs": sale["costs"],
            "volume": sale["volume"],
        })
        # if atts["name"] == 'Alpha Wolf HQ':
        #     print(str(sales_list[-1]))
        return sales_list

    # Return tuple with players ship/station info and ids
    def __calc_ship_info(self):
        info = []
        ids = []
        player_id = None
        for elem in self.xmltree.findall("./universe/component/connections//component[@owner='player']"):
            if "class" in elem.attrib and elem.attrib["class"] in ALL_CLASSES:
                try:
                    ship_type = None
                    ship_id = None
                    code = None
                    subordinates_cons = []
                    commander_cons = []
                    commander_id = None
                    commander_name = None
                    ship_class = elem.attrib["class"]
                    default_order = None

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

                    if ship_class in STATION_CLASSES:
                        # subordinate connections zoeken voor stations
                        for sub_con in elem.findall(".//connection[@connection='subordinates']"):
                            subordinates_cons.append(sub_con.attrib["id"])

                    # commander connections zoeken voor schepen
                    if ship_class in SHIP_CLASSES:
                        for com_con in elem.findall(".//connection[@connection='commander']/connected"):
                            commander_cons.append(com_con.attrib["connection"])
                        # default orders opzoeken
                        for d_order in elem.findall(".//orders/order[@default='1']"):
                            default_order = d_order.attrib["order"]

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
                        "default_order": default_order,
                    })
                    ids.append(ship_id)

                    if ship_class in PLAYER_CLASSES:
                        player_id = info[-1]["id"]

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
        return info, ids, player_id

    def get_id_attributes(self, ship_id):
        for c in self.own_ships:
            if c["id"] == ship_id:
                return c
        return None

    def hours_passed(self, time):
        return math.floor((self.game_time - time) / 3600)

    def get_profit(self, df):
        return df["value"].sum()

    # Schepen zonder trades, maar met trade orders
    def get_inactive_ships(self, hours):
        return None

    # Transacties per id
    def __calc_account_mutations(self):
        mutations = []
        for elem in self.xmltree.findall("./economylog/entries[@type='money']"):
            if "condensed" not in elem.attrib:
                for transaction in elem.findall(".//log"):
                    rec = {}
                    for a in ["time", "type", "owner", "v", "partner", "tradeentry"]:
                        if a in transaction.attrib:
                            rec[a] = transaction.attrib[a]
                        else:
                            rec[a] = None
                    # Alleen mutaties met owner en waarde
                    if rec["owner"] in self.own_ship_ids and rec["v"]:
                        mutations.append(rec)

                # sort by owner and then time
                mutations.sort(
                    key=lambda l: (l["owner"], l["time"])
                )

                length = len(mutations)
                for i in range(length):
                    previous = None
                    current = mutations[i]

                    # vorige mutatie
                    if i > 0:
                        previous = mutations[i-1]

                    value = 0
                    # mutatiewaarde
                    try:
                        if previous and current["owner"] == previous["owner"]:
                            value = float(current["v"])/100 - float(previous["v"])/100
                    except TypeError as e:
                        print("Unable to cast to float:\n" + str(previous) + "\n" + str(current))

                    mutations[i]["value"] = value

        # ["time", "type", "owner", "v", "partner", "tradeentry", value]
        # Transfers toevoegen aan sales. Mutaties van de player account tegenboeken
        sales_list = []
        for m in mutations:
            sales = 0
            costs = 0
            if float(m["value"]) >= 0:
                sales = float(m["value"])
            else:
                costs = float(m["value"])

            if m["type"] == 'transfer' and m["owner"] != self.player_id:

                sale = {
                    "time": m["time"],
                    "ship_id": m["owner"],
                    "value": m["value"],
                    "sales": sales,
                    "costs": costs,
                    "volume": 0,
                    "ware": 'ships/repairs',
                }
                # print("boeking", self.get_id_attributes(m["owner"])["name"], m["value"])
                sales_list.append(sale)

            # tegenboeking speler transfers naar stations
            elif m["type"] == 'transfer' and m["owner"] == self.player_id and m["partner"] in self.own_ship_ids:

                sale = {
                    "time": m["time"],
                    "ship_id": m["partner"],
                    "value": m["value"],
                    "sales": sales,
                    "costs": costs,
                    "volume": 0,
                    "ware": 'ships/repairs'
                }
                # print("tegenboeking", self.get_id_attributes(m["partner"])["name"], m["value"])
                sales_list.append(sale)

        # # debug sort
        # sales_list.sort(
        #     key=lambda l: (l["ship_id"], l["time"])
        # )
        # for e in sales_list:
        #     print(self.get_id_attributes(e["ship_id"])["name"], e["value"]])

        return sales_list
