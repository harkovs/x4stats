import datetime
import xml.etree.ElementTree as ET
import gzip
import pandas as pd
import numpy as np
import math
from pathlib import Path
import os
import time
import shutil
from stats.constants import ECO_ORDERS, SHIP_CLASSES, STATION_CLASSES, PLAYER_CLASSES, ALL_CLASSES, LOAD_MESSAGES
import random


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
        pd.set_option('display.max_rows', None)
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
            # Try to copy, if a same file error is raised pass since files are identical
            try:
                shutil.copy(p, p_to)
            except shutil.SameFileError:
                pass
            # trigger reload
            print(" * New save loading: " + str(p))
            self.reload(p_to)

    # (re)load save file
    def reload(self, save):

        process_start_time = datetime.datetime.now()

        assets = []
        trades = []
        transfers = []
        default_orders = []
        # Type of entry
        entries_type = None
        entries_condensed = False
        connections = []
        cur_player_entity = None
        cur_connection_type = None
        cur_connection_id = None
        connection_types = ['subordinates', 'commander']

        with gzip.open(save) as f:
            path = []
            xml = ET.iterparse(f, events=('start', 'end'))

            # Build path with every start and remove with every end event
            for event, elem in xml:
                if event == 'start':
                    path.append(elem.tag)
                    # Get game start time
                    if path == ['savegame', 'info', 'game']:
                        self.game_time = float(elem.attrib['time'])
                    elif path == ['savegame', 'economylog', 'entries']:
                        entries_type = elem.attrib['type']
                        # check for condensed money log
                        if 'condensed' in elem.attrib and elem.attrib['condensed'] == 1:
                            entries_condensed = True
                        else:
                            entries_condensed = False
                    # get trades
                    elif path == ['savegame', 'economylog', 'entries', 'log'] and entries_type == 'trade':
                        trades.append(elem.attrib)
                    # Get money transfers
                    elif path == ['savegame', 'economylog', 'entries', 'log'] and entries_type == 'money':
                        # Only include uncondensed transfers
                        if not entries_condensed:
                            transfers.append(elem.attrib)
                    # get player asset info
                    elif (path[0:4] == ['savegame', 'universe', 'component', 'connections']
                            and elem.tag == 'component'
                            and 'owner' in elem.attrib
                            and elem.attrib['owner'] == 'player'):
                        # store id for commander/subordinate connections
                        cur_player_entity = elem.attrib['id']
                        assets.append(elem.attrib)
                    # check for subordinates and commander connections
                    elif (cur_player_entity
                          and elem.tag == 'connection'
                          and elem.attrib['connection'] in connection_types):
                        cur_connection_type = elem.attrib['connection']
                        cur_connection_id = elem.attrib['id']
                    elif cur_player_entity and cur_connection_type in connection_types and elem.tag == 'connected':
                        connections.append({
                            "player_entity": cur_player_entity,
                            "connection_type": cur_connection_type,
                            "connection_id": cur_connection_id,
                            "connection": elem.attrib['connection']
                        })
                    # Get default order
                    elif (cur_player_entity
                          and elem.tag == 'order'
                          and 'default' in elem.attrib
                          and 'order' in elem.attrib):
                        default_orders.append({
                            'player_entity': cur_player_entity,
                            'order': elem.attrib['order']
                        })
                if event == 'end':
                    # remove current player ship entry
                    if (path[0:4] == ['savegame', 'universe', 'component', 'connections']
                          and elem.tag == 'component'
                          and 'owner' in elem.attrib
                          and elem.attrib['owner'] == 'player'):
                        cur_player_entity = None
                    # Remove connection type subordinates
                    elif (cur_player_entity
                          and elem.tag == 'connection'
                          and elem.attrib['connection'] in connection_types):
                        cur_connection_type = None
                        cur_connection_id = None
                    # remove last value in path
                    path.pop()
                    # clear elem from memory
                    elem.clear()

            process_end_time = datetime.datetime.now()
            process_time = process_end_time - process_start_time
            process_time = round(process_time.total_seconds(), 2)

            print(' * Processed xml in', str(process_time), 'seconds')

        # Find all player owned ships and stations
        self.own_ships, self.own_ship_ids, self.player_id = self.__calc_ship_info(
            assets=assets,
            connections=connections,
            orders=default_orders)
        self.print_random_load_msg()

        # calculate sales
        self.sales = self.__calc_sales(
            trades=trades,
            transfers=transfers
        )
        print(self.sales)
        self.print_random_load_msg()

        xml = None

        print(" * Loading complete")

    def get_game_time(self):
        return self.game_time

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
    def __calc_sales(self, trades, transfers):
        sales_list = []
        for elem in trades:

            try:
                if ('seller' in elem
                        and elem["seller"] in self.own_ship_ids
                        and "price" in elem):
                    volume = float(elem["v"])
                    # prijs is in centen
                    value = volume * float(elem["price"]) / 100
                    sales = volume * float(elem["price"]) / 100
                    sale = {
                        "time": elem["time"],
                        "ship_id": elem["seller"],
                        "value": value,
                        "sales": sales,
                        "costs": 0,
                        "volume": volume,
                        "ware": elem["ware"],
                    }
                    sales_list = self.__append_sales_list(sales_list, sale)

                    if "buyer" in elem and elem["buyer"] in self.own_ship_ids and "price" in elem:
                        volume = float(elem["v"])
                        value = -1 * volume * float(elem["price"]) / 100
                        costs = volume * float(elem["price"]) / 100
                        sale = {
                            "time": elem["time"],
                            "ship_id": elem["buyer"],
                            "value": value,
                            "sales": 0,
                            "costs": costs,
                            "volume": volume,
                            "ware": elem["ware"],
                        }
                        sales_list = self.__append_sales_list(sales_list, sale)

            except KeyError as e:
                print(str(type(e)))
                print(elem)
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
        account_mutations = self.__calc_account_mutations(transfers=transfers)
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
            print('No records found. Is the game version >= 4.00?')
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
    def __calc_ship_info(self, assets, connections, orders):
        info = []
        ids = []
        player_id = None

        for elem in assets:

            if "class" in elem and elem["class"] in ALL_CLASSES:

                try:
                    ship_type = None
                    ship_id = None
                    code = None
                    subordinates_cons = []
                    commander_cons = []
                    commander_id = None
                    commander_name = None
                    ship_class = elem["class"]
                    default_order = None

                    if "macro" in elem:
                        ship_type = elem["macro"]
                    if "id" in elem:
                        ship_id = elem["id"]
                    if "code" in elem:
                        code = elem["code"]
                    if "name" in elem:
                        name = elem["name"]
                    else:
                        name = code

                    if ship_class in STATION_CLASSES:
                        # subordinate connections zoeken voor stations
                        for con in connections:
                            if con['player_entity'] == ship_id and con['connection_type'] == 'subordinates':
                                subordinates_cons.append(con['connection_id'])

                    # commander connections zoeken voor schepen
                    if ship_class in SHIP_CLASSES:
                        for con in connections:
                            if con['player_entity'] == ship_id and con['connection_type'] == 'commander':
                                commander_cons.append(con["connection"])
                        # default orders opzoeken
                        for d_order in orders:
                            if d_order['player_entity'] == ship_id:
                                default_order = d_order["order"]

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
                    print(elem)

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
    def __calc_account_mutations(self, transfers):
        # print('mutations')
        mutations = []

        for transaction in transfers:
            rec = {}
            for a in ["time", "type", "owner", "v", "partner", "tradeentry"]:
                if a in transaction:
                    rec[a] = transaction[a]
                else:
                    rec[a] = None
            # Alleen mutaties met owner en waarde
            if rec["owner"] in self.own_ship_ids and rec["v"]:
                mutations.append(rec)

        # sort by owner and then time
        mutations.sort(
            key=lambda l: (l["owner"], l["time"])
        )

        # for m in mutations:
        #     if m["owner"] == "[0x39312]":
        #         print(m)

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

        # Mutaties restock en sell ship
        sales_list = []
        mutation_types = []
        for m in mutations:
            # print(m)
            sales = 0
            costs = 0
            if float(m["value"]) >= 0:
                sales = float(m["value"])
            else:
                costs = float(m["value"])

            if m["type"] in ('sellship', 'restock') and m["owner"] != self.player_id:

                sale = {
                    "time": m["time"],
                    "ship_id": m["owner"],
                    "value": m["value"],
                    "type": m['type'],
                    "sales": sales,
                    "costs": costs,
                    "volume": 0,
                    "ware": m["type"]
                }
                sales_list.append(sale)

            if m["type"] not in mutation_types:
                mutation_types.append(m["type"])

        print(mutation_types)
        return sales_list


    @staticmethod
    def print_random_load_msg():
        i = random.randint(0, len(LOAD_MESSAGES)-1)
        print(' *', LOAD_MESSAGES[i])

