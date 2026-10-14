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
from stats.constants import ECO_ORDERS, SHIP_CLASSES, STATION_CLASSES, PLAYER_CLASSES, BUILDSTORAGE_CLASSES, ALL_CLASSES, \
    LOAD_MESSAGES, SHIP_RACES, SHIP_ROLES
import random
import re


# "TST-ST Megaera (PUP-753) was destroyed."
LOSS_TITLE = re.compile(r"^(?P<name>.+?) \((?P<code>[A-Z]{3}-\d{3})\) was destroyed\.$")
# "TST-ST Vincejo in sector Eighteen Billion was destroyed by VIG Ice Union Plunderer Barbarossa."
LOSS_BY_TITLE = re.compile(r"^(?P<name>.+?) in sector (?P<location>.+?) was destroyed by (?P<attacker>.+?)\.$")
# "FD-TSM Runa Jung was forced to flee after being attacked by BUC Corsair Prometheus in Morning Star IV. ..."
ATTACKED_TITLE = re.compile(
    r"^(?P<name>.+?) was forced to flee after being attacked by (?P<attacker>.+?) in (?P<location>.+?)\. ")
# Station account mutations are stored as sales rows with the mutation type as ware. They are not trades or wares.
ACCOUNT_MUTATIONS = ["sellship", "restock"]


class X4stats:

    def __init__(self, save_location):

        self.is_ready = False
        self.xmltree = None
        self.game_time = None
        self.own_ships = None
        self.own_ship_ids = None
        self.assets_by_id = {}
        self.id_aliases = {}
        self.player_id = None
        self.sales = None
        self.save_location = save_location
        self.save_mtime = None
        self.game_guid = None
        self.loss_events = []
        # identifies the loaded save, set when a load completes; lets open pages notice a newer save
        self.save_version = None
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
            return True
        return False

    # (re)load save file
    def reload(self, save):

        process_start_time = datetime.datetime.now()

        assets = []
        trades = []
        transfers = []
        log_entries = []
        default_orders = []
        # non-default orders in queue order; the first one is being executed
        queued_orders = []
        # Type of entry
        entries_type = None
        entries_condensed = False
        connections = []
        listeners = []
        # (player entity id or None, path depth) for every open component. Components are nested (pilots in ships,
        # docked ships in stations), so the owning player entity has to be restored when a nested one closes.
        entity_stack = []
        cur_player_entity = None
        cur_connection_type = None
        cur_connection_id = None
        connection_types = ['subordinates', 'commander']
        # ids of all player owned components, known once the universe is read (it comes before the economy log). Used
        # to keep only the trades and transfers of the player, the log also has those of every other faction.
        player_ids = None

        with gzip.open(save) as f:
            path = []
            # open elements; a finished element is removed from its parent, elem.clear() alone leaves an empty
            # element behind for every node until its parent closes (the whole universe)
            elems = []
            xml = ET.iterparse(f, events=('start', 'end'))

            # Build path with every start and remove with every end event
            for event, elem in xml:
                if event == 'start':
                    path.append(elem.tag)
                    elems.append(elem)
                    # Get game start time
                    if path == ['savegame', 'info', 'game']:
                        self.game_time = float(elem.attrib['time'])
                        # identifies the playthrough across save files
                        self.game_guid = elem.attrib.get('guid')
                    # logbook messages about the player's own assets (attacks, losses, ...)
                    elif path == ['savegame', 'log', 'entry'] and elem.attrib.get('category') == 'upkeep':
                        log_entries.append(elem.attrib)
                    elif path == ['savegame', 'economylog']:
                        player_ids = {a['id'] for a in assets if 'id' in a}
                    elif path == ['savegame', 'economylog', 'entries']:
                        entries_type = elem.attrib['type']
                        # check for condensed money log
                        if elem.attrib.get('condensed') == '1':
                            entries_condensed = True
                        else:
                            entries_condensed = False
                    # get trades
                    elif path == ['savegame', 'economylog', 'entries', 'log'] and entries_type == 'trade':
                        if (player_ids is None or elem.attrib.get('seller') in player_ids
                                or elem.attrib.get('buyer') in player_ids):
                            trades.append(elem.attrib)
                    # Get money transfers
                    elif path == ['savegame', 'economylog', 'entries', 'log'] and entries_type == 'money':
                        # Only include uncondensed transfers
                        if not entries_condensed and (player_ids is None or elem.attrib.get('owner') in player_ids):
                            transfers.append(elem.attrib)
                    # get player asset info
                    elif (path[0:4] == ['savegame', 'universe', 'component', 'connections']
                            and elem.tag == 'component'):
                        if elem.attrib.get('owner') == 'player':
                            # store id for commander/subordinate connections
                            cur_player_entity = elem.attrib['id']
                            assets.append(elem.attrib)
                        elif 'owner' in elem.attrib:
                            cur_player_entity = None
                        # components without owner (storage, engines, ...) belong to their parent entity
                        entity_stack.append((cur_player_entity, len(path)))
                    # listeners of a player entity, used to link build storages to their station
                    elif (cur_player_entity
                          and elem.tag == 'listener'
                          and len(path) == entity_stack[-1][1] + 2
                          and 'listener' in elem.attrib):
                        listeners.append({
                            'player_entity': cur_player_entity,
                            'listener': elem.attrib['listener']
                        })
                    # check for subordinates and commander connections
                    elif (cur_player_entity
                          and elem.tag == 'connection'
                          and 'connection' in elem.attrib
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
                    # order queue of the entity itself (component/orders/order)
                    elif (cur_player_entity
                          and elem.tag == 'order'
                          and 'order' in elem.attrib
                          and path[-2] == 'orders'
                          and len(path) == entity_stack[-1][1] + 2):
                        queued_orders.append({
                            'player_entity': cur_player_entity,
                            'order': elem.attrib['order']
                        })
                if event == 'end':
                    # remove current player ship entry
                    if (path[0:4] == ['savegame', 'universe', 'component', 'connections']
                          and elem.tag == 'component'):
                        entity_stack.pop()
                        cur_player_entity = entity_stack[-1][0] if entity_stack else None
                    # Remove connection type subordinates
                    elif (cur_player_entity
                          and elem.tag == 'connection'
                          and 'connection' in elem.attrib
                          and elem.attrib['connection'] in connection_types):
                        cur_connection_type = None
                        cur_connection_id = None
                    # remove last value in path
                    path.pop()
                    # clear elem from memory
                    elem.clear()
                    elems.pop()
                    if elems:
                        # earlier siblings are already removed, so this is the only child
                        elems[-1].remove(elem)

            process_end_time = datetime.datetime.now()
            process_time = process_end_time - process_start_time
            process_time = round(process_time.total_seconds(), 2)

            print(' * Processed xml in', str(process_time), 'seconds')

        # Find all player owned ships and stations
        own_ships, player_id = self.__calc_ship_info(
            assets=assets,
            connections=connections,
            orders=default_orders,
            queued_orders=queued_orders)
        id_aliases = self.__calc_buildstorage_aliases(own_ships=own_ships, assets=assets, listeners=listeners)
        self.own_ships = own_ships
        self.player_id = player_id
        self.id_aliases = id_aliases
        # looked up for every trade, so keep these O(1)
        self.own_ship_ids = {s["id"] for s in own_ships}
        self.assets_by_id = {s["id"]: s for s in own_ships}
        self.print_random_load_msg()

        # calculate sales
        self.loss_events = self.__calc_loss_events(log_entries)

        self.sales = self.__calc_sales(
            trades=trades,
            transfers=transfers
        )
        print(self.sales)
        self.print_random_load_msg()

        xml = None

        # stays the same across a restart on the same save, changes for any other save
        self.save_version = f"{self.game_guid}:{self.game_time}:{self.save_mtime}"
        print(" * Loading complete")

    def get_game_time(self):
        return self.game_time

    def get_save_version(self):
        return self.save_version

    def get_game_guid(self):
        return self.game_guid

    def get_loss_events(self):
        return self.loss_events

    # Own ships and stations with their commander and orders, to remember what lost assets were doing
    def get_fleet(self):
        return [{
            "id": s["id"],
            "code": s["code"],
            "name": s["name"],
            "ship_type": s["type"],
            "commander": s["direct_commander_name"],
            "default_order": s["default_order"],
            "orders": " > ".join(s["orders"]) or None,
        } for s in self.own_ships if s["class"] in SHIP_CLASSES + STATION_CLASSES]

    def get_player_name(self):
        player = self.get_id_attributes(self.player_id) if self.player_id else None
        return player["name"] if player else None

    # exclude_internal: leave out trades between own assets, which net to zero but would count twice in totals over
    # all assets (sales of one asset and costs of another)
    def get_df_sales(self, hours=None, filter_zero_value=False, exclude_internal=False):
        df = self.sales.copy()
        if hours:
            # uren beginnen te tellen bij 0. Laatste 1 uur is dus uur <= 0
            hours = int(hours) - 1
            df = df.query("hours_since_event <= " + str(hours))
        if filter_zero_value:
            df = df.query("value != 0")
        if exclude_internal:
            df = df[~df["internal"]]

        return df

    def get_df_sales_sorted(self, hours=None, filter_zero_value=False):
        df = self.get_df_sales(hours, filter_zero_value)
        df = df.sort_values(["ship_name", "time"])
        return df

    def get_df_per_ship(self, hours=None):
        return self.__calc_df_per_ship(hours)

    def __calc_df_per_ship(self, hours=None):
        df = self.get_df_sales(hours)
        return self.__aggregate_ships(df.assign(trades=self.__trade_flags(df)))

    # a trade is a row with a ware and a value; zero-value filler rows and account mutations don't count
    @staticmethod
    def __trade_flags(df):
        return (df["ware"].notna() & ~df["ware"].isin(ACCOUNT_MUTATIONS) & (df["value"] != 0)).astype(int)

    # Sales rows (with a trades column) -> one row per ship/station
    def __aggregate_ships(self, df, extra_columns=()):
        df_per_ship = df.groupby(["ship_id", "ship_class", "commander_id", "commander_name", "default_order", "ship_code",
                                  "ship_name", "ship_type"], dropna=False)[
            ["value", "sales", "costs", "volume", "trades", *extra_columns]].sum().reset_index()
        df_per_ship["ship_type_name"] = df_per_ship["ship_type"].map(self.ship_type_label)

        df_per_ship = self.__per_x_help(df_per_ship)

        return df_per_ship

    # Ships only (no stations/player), ranked by profit
    def get_df_ships(self, hours=None):
        df = self.__calc_df_per_ship(hours)
        df = df[df["ship_class"].isin(SHIP_CLASSES)].copy()
        df["profit_per_trade"] = (df["value"] / df["trades"].where(df["trades"] > 0)).fillna(0).round(0)
        return df.sort_values("value", ascending=False)

    # Aggregate ships per ship type (macro)
    def get_df_per_ship_type(self, hours=None):
        df = self.get_df_ships(hours)
        df_per_type = df.groupby(["ship_type", "ship_type_name", "ship_class"], dropna=False).agg(
            ships=("ship_id", "nunique"),
            trades=("trades", "sum"),
            value=("value", "sum"),
            sales=("sales", "sum"),
            costs=("costs", "sum"),
            volume=("volume", "sum"),
        ).reset_index()
        df_per_type = self.__per_x_help(df_per_type)
        df_per_type["profit_per_ship"] = (df_per_type["value"] / df_per_type["ships"]).round(0)
        df_per_type["trades_per_ship"] = (df_per_type["trades"] / df_per_type["ships"]).round(1)
        return df_per_type.sort_values("value", ascending=False)

    # ship_bor_m_miner_solid_01_a_macro -> "Boron M Miner (solid) 01". Falls back to the macro for other shapes.
    @staticmethod
    def ship_type_label(macro):
        if not isinstance(macro, str):
            return macro
        parts = macro.split("_")
        if len(parts) < 6 or parts[0] != "ship" or parts[-1] != "macro":
            return macro
        race, size, number, variant = parts[1], parts[2], parts[-3], parts[-2]
        role = "_".join(parts[3:-3])
        label = " ".join([
            SHIP_RACES.get(race, race.upper()),
            size.upper(),
            SHIP_ROLES.get(role, role.replace("_", " ").capitalize()),
        ]).strip()
        return f"{label} {number}" + (variant if variant != "a" else "")

    # geen trade waarde in de laatste X uren, maar wel trade orders
    def get_idle_traders_miners(self, hours):
        df = self.__calc_df_per_ship(hours)
        return df.loc[
            (df['default_order'].isin(ECO_ORDERS))
            & (df['ship_class'].isin(SHIP_CLASSES))
            & (df['trades'] == 0)
        ]

    # df['ship_class'].isin(SHIP_CLASSES), df['value'] == 0

    # (active, total) count of ships with a trade/mining order
    def get_active_traders_count(self, hours=None):
        df = self.__calc_df_per_ship(hours)
        eligible = df.loc[
            (df['default_order'].isin(ECO_ORDERS))
            & (df['ship_class'].isin(SHIP_CLASSES))
        ]
        active = eligible.loc[eligible['trades'] > 0]
        return len(active), len(eligible)

    def get_df_per_commander(self, hours=None):
        return self.__calc_df_per_commander(hours)

    def __calc_df_per_commander(self, hours=None):
        df = self.get_df_sales(hours)
        # trades within the group cancel out, leaving them in would only inflate sales/costs/volume
        df = df[~df["intra_group"]]
        df_per_com = df[["commander_id", "commander_name", "value", "sales", "costs", "volume"]] \
            .groupby(["commander_id", "commander_name"]
                     , dropna=False).sum().reset_index()
        df_per_com = self.__per_x_help(df_per_com)
        return df_per_com

    # Wares bought and sold by one commander group (commander and its subordinates), trades within the group left out
    def get_df_commander_wares(self, commander_id, hours=None):
        df = self.get_df_sales(hours, filter_zero_value=True)
        df = df[(df["commander_id"] == commander_id) & ~df["intra_group"]]
        return self.__aggregate_wares(df).sort_values(["sales", "value"], ascending=False)

    # Ships and stations of one commander group. Value/sales/costs/volume leave out trades within the group, so they add
    # up to the commander totals; those go in group_value instead (+ delivered to the group, - taken from it). The
    # trade count includes them, so a miner that only delivers to its station doesn't look idle.
    def get_df_commander_ships(self, commander_id, hours=None):
        df = self.get_df_sales(hours)
        df = df[df["commander_id"] == commander_id]
        external = ~df["intra_group"]
        df = df.assign(trades=self.__trade_flags(df),
                       group_value=df["value"].where(~external, 0),
                       value=df["value"].where(external, 0),
                       sales=df["sales"].where(external, 0),
                       costs=df["costs"].where(external, 0),
                       volume=df["volume"].where(external, 0))
        return self.__aggregate_ships(df, extra_columns=["group_value"]).sort_values("value", ascending=False)

    def get_df_per_ware(self, hours=None):
        return self.__calc_df_per_ware(hours)

    def __calc_df_per_ware(self, hours=None):
        df = self.get_df_sales(hours, filter_zero_value=True, exclude_internal=True)
        return self.__aggregate_wares(df).sort_values("value", ascending=False)

    # Sales rows -> one row per ware, with sold and bought volume split out
    def __aggregate_wares(self, df):
        df = df[df["ware"].notna() & ~df["ware"].isin(ACCOUNT_MUTATIONS)]
        df = df.assign(sold_volume=df["volume"].where(df["sales"] > 0, 0),
                       bought_volume=df["volume"].where(df["costs"] > 0, 0))
        df_per_ware = df[["ware", "value", "sales", "costs", "volume", "sold_volume", "bought_volume"]] \
            .groupby(["ware"], dropna=False).sum().reset_index()
        return self.__per_x_help(df_per_ware)

    def get_df_per_hour_ware(self, hours=None):
        return self.__calc_df_per_hour_ware(hours)

    def __calc_df_per_hour_ware(self, hours=None):
        df = self.get_df_sales(hours, filter_zero_value=True, exclude_internal=True)
        df = df[df["ware"].notna() & ~df["ware"].isin(ACCOUNT_MUTATIONS)]
        df_per_hour_ware = df[["hours_since_event", "ware", "value", "sales", "costs", "volume"]] \
            .groupby(["hours_since_event", "ware"], dropna=False).sum().reset_index()
        df_per_hour_ware = self.__per_x_help(df_per_hour_ware)
        df_per_hour_ware = df_per_hour_ware.sort_values("hours_since_event", ascending=False)
        return df_per_hour_ware

    # Margekolom en afronding
    @staticmethod
    def __per_x_help(df_perx):
        df_perx["margin"] = (df_perx["sales"] - df_perx["costs"]) / df_perx["sales"]
        df_perx.loc[df_perx.margin < -1, 'margin'] = -1
        df_perx["margin"] = df_perx["margin"].replace([-np.inf, np.nan], 0)

        # afronden
        cols = ["value", "sales", "costs", "volume", "margin"]
        df_perx[cols] = df_perx[cols].round({"value": 0, "sales": 0, "costs": 0, "volume": 0, "margin": 4})

        return df_perx

    # Loop through all trade transactions to collect transactions where the player is seller or buyer
    def __calc_sales(self, trades, transfers):
        sales_list = []
        for elem in trades:
            # attribute build storage trades to the station being built
            if elem.get("seller") in self.id_aliases or elem.get("buyer") in self.id_aliases:
                elem = dict(elem)
                for role in ("seller", "buyer"):
                    if elem.get(role) in self.id_aliases:
                        elem[role] = self.id_aliases[elem[role]]

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
                        "partner_id": elem.get("buyer"),
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
                        "partner_id": elem.get("seller"),
                    }
                    sales_list = self.__append_sales_list(sales_list, sale)

            except KeyError as e:
                print(str(type(e)))
                print(elem)
                raise

        # Add ships with trade/mine orders and stations to make sure they are displayed even without trade value.
        for ship in self.own_ships:
            if ship["class"] in (SHIP_CLASSES + STATION_CLASSES + PLAYER_CLASSES) or ship["default_order"]:
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
        # A trade with another asset under the same commander (e.g. a station's miner selling to that station) shows
        # up as a sale on one side and a purchase on the other. It nets to zero for the commander, but would inflate
        # its sales, costs and volume.
        partner_id = sale.get("partner_id")
        partner = self.get_id_attributes(partner_id)
        sales_list.append({
            "ship_id": sale["ship_id"],
            "ship_type": atts["type"],
            "ship_class": atts["class"],
            "ship_name": atts["name"],
            "ship_code": atts["code"],
            "commander_id": atts["commander_id"],
            "commander_name": atts["commander_name"],
            "partner_id": partner_id,
            # trade with another own asset: both sides are in the data, so totals over all assets count it twice
            "internal": partner is not None,
            "intra_group": partner is not None and partner["commander_id"] == atts["commander_id"],
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

    # Return tuple with players ship/station info and the player id
    def __calc_ship_info(self, assets, connections, orders, queued_orders):
        info = []
        player_id = None

        # index by entity once instead of scanning all connections/orders for every asset
        subordinate_cons_by_entity = {}
        commander_cons_by_entity = {}
        for con in connections:
            if con['connection_type'] == 'subordinates':
                subordinate_cons_by_entity.setdefault(con['player_entity'], []).append(con['connection_id'])
            elif con['connection_type'] == 'commander':
                commander_cons_by_entity.setdefault(con['player_entity'], []).append(con['connection'])
        default_order_by_entity = {o['player_entity']: o['order'] for o in orders}
        queued_orders_by_entity = {}
        for o in queued_orders:
            queued_orders_by_entity.setdefault(o['player_entity'], []).append(o['order'])

        for elem in assets:

            if "class" in elem and elem["class"] in ALL_CLASSES:

                try:
                    ship_type = None
                    ship_id = None
                    code = None
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
                    # "{page,id}" names are untranslated text references, show the code instead
                    if "name" in elem and not elem["name"].startswith("{"):
                        name = elem["name"]
                    else:
                        name = code

                    # subordinate connections (stations en schepen kunnen commander zijn)
                    subordinates_cons = subordinate_cons_by_entity.get(ship_id, [])

                    # commander connections en default order voor schepen
                    if ship_class in SHIP_CLASSES:
                        commander_cons = commander_cons_by_entity.get(ship_id, [])
                        default_order = default_order_by_entity.get(ship_id)

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
                        "orders": queued_orders_by_entity.get(ship_id, []),
                    })

                    if ship_class in PLAYER_CLASSES:
                        player_id = info[-1]["id"]

                except KeyError as e:
                    print(str(e))
                    print(elem)

        # direct commander of every asset with exactly 1 commander connection
        commander_by_con = {con: c for c in info for con in c["subordinate_cons"]}
        direct_commander = {}
        for e in info:
            if len(e["commander_cons"]) == 1 and e["commander_cons"][0] in commander_by_con:
                direct_commander[e["id"]] = commander_by_con[e["commander_cons"][0]]

        # Group under the top of the chain (station -> ship -> wing ship all go to the station), so a group always
        # contains its commander. Bij geen (gevonden) commander ben je eigen baas.
        for e in info:
            top = e
            seen = {e["id"]}
            while top["id"] in direct_commander and direct_commander[top["id"]]["id"] not in seen:
                top = direct_commander[top["id"]]
                seen.add(top["id"])
            e["commander_id"] = top["id"]
            e["commander_name"] = top["name"]
            e["direct_commander_name"] = direct_commander[e["id"]]["name"] if e["id"] in direct_commander else None

        return info, player_id

    # Map player build storage ids to the id of the station they build. A station lists its build storage as a
    # 'killed' listener. Build storages without a station are kept as their own entry so their trades still count.
    def __calc_buildstorage_aliases(self, own_ships, assets, listeners):
        aliases = {}
        station_ids = {s["id"] for s in own_ships if s["class"] in STATION_CLASSES}
        for elem in assets:
            if elem.get("class") not in BUILDSTORAGE_CLASSES:
                continue
            bs_id = elem["id"]
            for lis in listeners:
                if lis["listener"] == bs_id and lis["player_entity"] in station_ids:
                    aliases[bs_id] = lis["player_entity"]
                    break
            else:
                name = "Build storage " + elem.get("code", bs_id)
                own_ships.append({
                    "type": elem.get("macro"),
                    "id": bs_id,
                    "name": name,
                    "code": elem.get("code"),
                    "subordinate_cons": [],
                    "commander_cons": [],
                    "class": elem["class"],
                    "commander_id": bs_id,
                    "commander_name": name,
                    "default_order": None,
                    "orders": [],
                    "direct_commander_name": None,
                })
        return aliases

    def get_id_attributes(self, ship_id):
        return self.assets_by_id.get(ship_id)

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
            key=lambda l: (l["owner"], float(l["time"]))
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
                costs = -float(m["value"])

            if m["type"] in ACCOUNT_MUTATIONS and m["owner"] != self.player_id:

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


    # Turn logbook messages into destroyed/attacked events. The messages are localised game text, so this only
    # recognises the English wording; other upkeep messages are ignored.
    @staticmethod
    def __calc_loss_events(log_entries):
        events = []
        for entry in log_entries:
            title = entry.get("title", "")
            # multi-line text uses a literal "[\012]" as line separator
            text = entry.get("text", "").replace("[\\012]", "\n")
            details = {}
            for line in text.split("\n"):
                key, sep, value = line.partition(": ")
                if sep:
                    details[key.strip()] = value.strip()

            event = None
            m = LOSS_TITLE.match(title)
            if m:
                event = {"kind": "destroyed", "name": m["name"], "code": m["code"],
                         "location": details.get("Location"), "commander": details.get("Commander"),
                         "attacker": details.get("Destroyed by")}
            elif LOSS_BY_TITLE.match(title):
                m = LOSS_BY_TITLE.match(title)
                event = {"kind": "destroyed", "name": m["name"], "code": None, "location": m["location"],
                         "commander": None, "attacker": m["attacker"]}
            elif ATTACKED_TITLE.match(title):
                m = ATTACKED_TITLE.match(title)
                event = {"kind": "attacked", "name": m["name"], "code": None, "location": m["location"],
                         "commander": None, "attacker": m["attacker"]}
            elif " was destroyed" in title:
                # unknown wording (e.g. stations): keep it so nothing is silently lost
                event = {"kind": "destroyed", "name": title.split(" was destroyed")[0], "code": None,
                         "location": details.get("Location"), "commander": details.get("Commander"),
                         "attacker": details.get("Destroyed by")}

            if event:
                # the logbook entry links to the own asset it is about, which survives renames
                event.update({"time": float(entry["time"]), "title": title, "text": text,
                              "asset_id": entry.get("component")})
                events.append(event)
        return events

    @staticmethod
    def print_random_load_msg():
        i = random.randint(0, len(LOAD_MESSAGES)-1)
        print(' *', LOAD_MESSAGES[i])

