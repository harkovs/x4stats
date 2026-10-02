# trade or mining orders
ECO_ORDERS = [
    'MiningRoutine_Basic'
    , 'MiningRoutine'
    , 'MiningRoutine_Advanced'
    , 'MiddleMan'
    , 'TradeRoutine'
    , 'TradeRoutine_Basic'
    , 'TradeRoutine_Advanced'
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
# Construction storage of a player station. Its trades are attributed to the station it builds.
BUILDSTORAGE_CLASSES = ['buildstorage']
ALL_CLASSES = SHIP_CLASSES + STATION_CLASSES + PLAYER_CLASSES

# Ship macros look like ship_<race>_<size>_<role>_<nn>_<variant>_macro. Used to build readable ship type labels.
SHIP_RACES = {
    'arg': 'Argon',
    'atf': 'Terran (ATF)',
    'bor': 'Boron',
    'gen': 'Generic',
    'kha': "Kha'ak",
    'par': 'Paranid',
    'pir': 'Pirate',
    'spl': 'Split',
    'tel': 'Teladi',
    'ter': 'Terran',
    'xen': 'Xenon',
    'yak': 'Yaki',
}
SHIP_ROLES = {
    'miner_solid': 'Miner (solid)',
    'miner_liquid': 'Miner (liquid)',
    'trans_container': 'Transport (container)',
    'trans_condensate': 'Transport (condensate)',
    'heavyfighter': 'Heavy fighter',
    'fightingdrone': 'Fighting drone',
    'cv': 'Construction vessel',
}

LOAD_MESSAGES = [
    'Spawning Khaak base',
    'Buffing Xenon',
    'Reticulating splines',
    'Hacking security terminal',
    'Lowering faction reputation',
    'Setting modified flag',
    'Teleporting player HQ to Matrix #79B',
    'Declaring war on the Argon',
    'Erasing HOP stations',
    'Updating trade offers',
    'Sabotaging player stations',
    'Training auto pilot',
    'Installing jump drives',
    'Deconstructing super highways'
]
