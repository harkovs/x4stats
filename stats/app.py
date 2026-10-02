import math
import socket
import sys
import threading
import time
from flask import Flask
from flask import g, jsonify, render_template, redirect, request, url_for
from stats.x4stats import X4stats
from stats.events import EventStore
from stats.notify import TelegramNotifier, format_event
from pathlib import Path

app = Flask(__name__)
app.config.from_pyfile('config.py')
app.debug = False
app.template_folder = 'templates'
app.static_folder = 'static'

# Check config
save_location = app.config["SAVE_LOCATION"]
p = Path(save_location)
if not p.exists():
    print("SAVE_LOCATION does not exist. Check config.py file.")
    quit()

HOST = '127.0.0.1'
PORT = 2992

# Optional settings, see config.example.py
EVENTS_DB = app.config.get('EVENTS_DB', str(Path(app.root_path) / 'saves' / 'events.sqlite'))
AUTO_RELOAD_SECONDS = app.config.get('AUTO_RELOAD_SECONDS', 60)
TELEGRAM_BOT_TOKEN = app.config.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = app.config.get('TELEGRAM_CHAT_ID')
TELEGRAM_NOTIFY_ATTACKS = app.config.get('TELEGRAM_NOTIFY_ATTACKS', False)
# More new events than this in one save are summarised instead of sent one by one
TELEGRAM_MAX_MESSAGES = 10

# Loaded in main(), after the port check, so a second instance doesn't parse the whole save first
x4stats = None
event_store = None
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else None

# Requests and the background save check both use x4stats; a reload must not change it halfway through a request
data_lock = threading.RLock()


@app.before_request
def lock_data():
    # the save status poll only reads one value and must answer while a reload is running
    if request.endpoint == 'save_status':
        return
    data_lock.acquire()
    g.data_locked = True


@app.teardown_request
def unlock_data(exc):
    if g.pop('data_locked', False):
        data_lock.release()


# Store loss/attack events of the loaded save and send notifications for ones not seen before
def sync_events():
    new, first_import = event_store.record(x4stats.get_game_guid(), x4stats.get_loss_events())
    if new:
        print(f" * {len(new)} new loss/attack events" + (" (first import, no notifications)" if first_import else ""))
    if not notifier or first_import:
        return
    to_send = [e for e in sorted(new, key=lambda e: e['time'])
               if e['kind'] == 'destroyed' or TELEGRAM_NOTIFY_ATTACKS]
    if not to_send:
        return
    messages = [format_event(e) for e in to_send[:TELEGRAM_MAX_MESSAGES]]
    if len(to_send) > TELEGRAM_MAX_MESSAGES:
        messages.append(f"X4: ... and {len(to_send) - TELEGRAM_MAX_MESSAGES} more events, see the Losses page")
    # send outside the request/reload so a slow network doesn't hold the data lock
    threading.Thread(target=lambda: [notifier.send(m) for m in messages], daemon=True).start()


def refresh_save():
    with data_lock:
        if x4stats.check_for_new_file():
            sync_events()


def poll_saves(interval):
    while True:
        time.sleep(interval)
        try:
            refresh_save()
        except Exception as e:
            print(" * Background save check failed:", type(e).__name__, e)


def number_formatter(n):
    return f'{int(n):,}'.replace(',', '.')


app.jinja_env.filters['money'] = number_formatter


# Shared values for the sidebar on every page
@app.context_processor
def inject_shell():
    return {
        'player_name': x4stats.get_player_name(),
        'game_hours': round(x4stats.get_game_time() / 3600, 1),
        'save_version': x4stats.get_save_version(),
    }


def get_commander_chart_data(df):
    df = df.sort_values('value', ascending=False)
    return {
        'labels': [str(v) for v in df['commander_name']],
        'values': [float(v) for v in df['value']],
    }


def get_scatter_data(df):
    df = df.sort_values('value', ascending=False)
    if len(df) == 0:
        return []
    vol_min = float(df['volume'].min())
    vol_max = float(df['volume'].max())

    def radius(v):
        if vol_max == vol_min:
            return 10.0
        return 6.0 + (float(v) - vol_min) / (vol_max - vol_min) * 18.0

    return [
        {
            'x': float(row['value']),
            'y': float(row['margin']),
            'r': radius(row['volume']),
            'label': str(row['commander_name']),
        }
        for _, row in df.iterrows()
    ]


def get_ware_pie_data(df, column):
    df = df[df[column] > 0].sort_values(column, ascending=False)
    return {
        'labels': [str(v) for v in df['ware']],
        'values': [float(v) for v in df[column]],
    }


def get_ware_time_series_data(df):
    hours = sorted(df['hours_since_event'].unique(), reverse=True)
    wares = sorted(df['ware'].unique())
    labels = ['now' if h == 0 else f'-{int(h)}h' for h in hours]

    def series_for(column):
        pivoted = df.set_index(['hours_since_event', 'ware'])[column].unstack('ware')
        pivoted = pivoted.reindex(index=hours, columns=wares)
        return {w: [None if math.isnan(v) else float(v) for v in pivoted[w]] for w in wares}

    profit_by_ware = series_for('value')
    margin_by_ware = series_for('margin')
    volume_by_ware = series_for('volume')

    series = {
        w: {'profit': profit_by_ware[w], 'margin': margin_by_ware[w], 'volume': volume_by_ware[w]}
        for w in wares
    }
    return {'labels': labels, 'wares': wares, 'series': series}


def get_bar_data(df, label_column, value_column):
    return {
        'labels': [str(v) for v in df[label_column]],
        'values': [float(v) for v in df[value_column]],
    }


def table_columns_ship(df):
    return [{'key': c, 'label': c, 'type': (
        'money' if c == 'value' else
        'number' if c in ('sales', 'costs', 'volume', 'trades') else
        'percent' if c == 'margin' else
        'text'
    )} for c in df.columns]


TABLE_COLUMNS_INACTIVE = [
    {'key': 'commander_name', 'label': 'commander_name', 'type': 'text'},
    {'key': 'default_order', 'label': 'default_order', 'type': 'text'},
    {'key': 'ship_code', 'label': 'ship_code', 'type': 'text'},
    {'key': 'ship_name', 'label': 'ship_name', 'type': 'text'},
    {'key': 'ship_type', 'label': 'ship_type', 'type': 'text'},
    {'key': 'value', 'label': 'value', 'type': 'money'},
    {'key': 'volume', 'label': 'volume', 'type': 'number'},
]

TABLE_COLUMNS_WARE = [
    {'key': 'ware', 'label': 'ware', 'type': 'text'},
    {'key': 'volume', 'label': 'volume traded', 'type': 'number'},
    {'key': 'costs', 'label': 'total bought', 'type': 'number'},
    {'key': 'sales', 'label': 'total sales', 'type': 'number'},
    {'key': 'value', 'label': 'profit', 'type': 'money'},
    {'key': 'margin', 'label': 'margin', 'type': 'percent'},
]

TABLE_COLUMNS_SHIP_TYPE = [
    {'key': 'ship_type_name', 'label': 'ship type', 'type': 'text'},
    {'key': 'ships', 'label': 'ships', 'type': 'number'},
    {'key': 'trades', 'label': 'trades', 'type': 'number'},
    {'key': 'trades_per_ship', 'label': 'trades / ship', 'type': 'decimal'},
    {'key': 'sales', 'label': 'total sales', 'type': 'number'},
    {'key': 'costs', 'label': 'total bought', 'type': 'number'},
    {'key': 'value', 'label': 'profit', 'type': 'money'},
    {'key': 'profit_per_ship', 'label': 'profit / ship', 'type': 'money'},
    {'key': 'margin', 'label': 'margin', 'type': 'percent'},
]

TABLE_COLUMNS_SHIPS = [
    {'key': 'ship_name', 'label': 'name', 'type': 'text'},
    {'key': 'ship_code', 'label': 'code', 'type': 'text'},
    {'key': 'ship_type_name', 'label': 'ship type', 'type': 'text'},
    {'key': 'commander_name', 'label': 'commander', 'type': 'text'},
    {'key': 'default_order', 'label': 'order', 'type': 'text'},
    {'key': 'trades', 'label': 'trades', 'type': 'number'},
    {'key': 'volume', 'label': 'volume', 'type': 'number'},
    {'key': 'value', 'label': 'profit', 'type': 'money'},
    {'key': 'profit_per_trade', 'label': 'profit / trade', 'type': 'money'},
    {'key': 'margin', 'label': 'margin', 'type': 'percent'},
]

TABLE_COLUMNS_TOP_SHIPS = [
    {'key': 'ship_name', 'label': 'ship', 'type': 'text'},
    {'key': 'trades', 'label': 'trades', 'type': 'number'},
    {'key': 'value', 'label': 'profit', 'type': 'money'},
]

TABLE_COLUMNS_TOP_WARES = [
    {'key': 'ware', 'label': 'ware', 'type': 'text'},
    {'key': 'volume', 'label': 'volume traded', 'type': 'number'},
    {'key': 'value', 'label': 'profit', 'type': 'money'},
    {'key': 'margin', 'label': 'margin', 'type': 'percent'},
]

TABLE_COLUMNS_DESTROYED = [
    {'key': 'game_hours', 'label': 'game time (h)', 'type': 'decimal'},
    {'key': 'hours_ago', 'label': 'hours ago', 'type': 'number'},
    {'key': 'name', 'label': 'name', 'type': 'text'},
    {'key': 'code', 'label': 'code', 'type': 'text'},
    {'key': 'location', 'label': 'location', 'type': 'text'},
    {'key': 'commander', 'label': 'commander', 'type': 'text'},
    {'key': 'attacker', 'label': 'destroyed by', 'type': 'text'},
]

TABLE_COLUMNS_ATTACKED = [
    {'key': 'game_hours', 'label': 'game time (h)', 'type': 'decimal'},
    {'key': 'hours_ago', 'label': 'hours ago', 'type': 'number'},
    {'key': 'name', 'label': 'name', 'type': 'text'},
    {'key': 'location', 'label': 'location', 'type': 'text'},
    {'key': 'attacker', 'label': 'attacked by', 'type': 'text'},
]

TABLE_COLUMNS_TRANSACTIONS = [
    {'key': 'ship_name', 'label': 'name', 'type': 'text'},
    {'key': 'ship_code', 'label': 'code', 'type': 'text'},
    {'key': 'commander_name', 'label': 'commander', 'type': 'text'},
    {'key': 'time', 'label': 'time', 'type': 'number'},
    {'key': 'hours_since_event', 'label': 'hours ago', 'type': 'number'},
    {'key': 'ware', 'label': 'ware', 'type': 'text'},
    {'key': 'value', 'label': 'value', 'type': 'money'},
    {'key': 'volume', 'label': 'volume', 'type': 'number'},
]


def hours_context(hours):
    # "look back N hours" path segment -> display text + raw value for links
    if hours:
        return {'hours': "past " + str(hours) + " hours", 'hours_raw': hours}
    return {'hours': "all time", 'hours_raw': ''}


def value_class(v):
    return 'positive' if v > 0 else 'negative' if v < 0 else ''


# Pages the "Update save" link may return to
PAGES = ['stats', 'trends', 'commanders', 'wares', 'ships', 'idle', 'losses', 'transactions']


@app.route('/', methods=['GET'])
def index():
    return redirect(url_for('stats'))


@app.route('/stats', methods=['GET'])
@app.route('/stats/<int:hours>', methods=['GET'])
def stats(hours=None):
    df_sales = x4stats.get_df_sales(hours, filter_zero_value=True)
    df_per_ware = x4stats.get_df_per_ware(hours)
    df_ships = x4stats.get_df_ships(hours)

    profit_value = float(x4stats.get_profit(df_sales))
    total_sales = float(df_sales['sales'].sum())
    total_costs = float(df_sales['costs'].sum())
    margin_value = (total_sales - total_costs) / total_sales if total_sales else 0.0
    active_count, eligible_count = x4stats.get_active_traders_count(hours)

    return render_template(
        'index.html',
        game_time=str(round(x4stats.get_game_time() / 3600, 2)),
        profit_value=profit_value,
        profit_class=value_class(profit_value),
        total_sales=total_sales,
        total_costs=total_costs,
        margin_value=margin_value,
        margin_class=value_class(margin_value),
        active_count=active_count,
        eligible_count=eligible_count,
        idle_count=len(x4stats.get_idle_traders_miners(hours)),
        lost_count=sum(1 for e in get_loss_events(hours) if e['kind'] == 'destroyed'),
        top_ship_columns=TABLE_COLUMNS_TOP_SHIPS,
        top_ship_rows=df_ships.head(5).to_dict('records'),
        top_ware_columns=TABLE_COLUMNS_TOP_WARES,
        top_ware_rows=df_per_ware.head(5).to_dict('records'),
        **hours_context(hours),
    )


@app.route('/trends', methods=['GET'])
@app.route('/trends/<int:hours>', methods=['GET'])
def trends(hours=None):
    return render_template(
        'trends.html',
        time_series=get_ware_time_series_data(x4stats.get_df_per_hour_ware(hours)),
        **hours_context(hours),
    )


@app.route('/commanders', methods=['GET'])
@app.route('/commanders/<int:hours>', methods=['GET'])
def commanders(hours=None):
    df_per_commander = x4stats.get_df_per_commander(hours)
    return render_template(
        'commanders.html',
        commander_chart=get_commander_chart_data(df_per_commander),
        scatter_data=get_scatter_data(df_per_commander),
        **hours_context(hours),
    )


@app.route('/wares', methods=['GET'])
@app.route('/wares/<int:hours>', methods=['GET'])
def wares(hours=None):
    df_per_ware = x4stats.get_df_per_ware(hours)
    return render_template(
        'wares.html',
        sales_pie=get_ware_pie_data(df_per_ware, 'sales'),
        costs_pie=get_ware_pie_data(df_per_ware, 'costs'),
        ware_columns=TABLE_COLUMNS_WARE,
        ware_rows=df_per_ware.to_dict('records'),
        **hours_context(hours),
    )


@app.route('/idle', methods=['GET'])
@app.route('/idle/<int:hours>', methods=['GET'])
def idle(hours=None):
    return render_template(
        'idle.html',
        inactive_columns=TABLE_COLUMNS_INACTIVE,
        inactive_rows=x4stats.get_idle_traders_miners(hours).to_dict('records'),
        **hours_context(hours),
    )


@app.route('/ships', methods=['GET'])
@app.route('/ships/<int:hours>', methods=['GET'])
def ships(hours=None):
    df_ships = x4stats.get_df_ships(hours)
    df_per_type = x4stats.get_df_per_ship_type(hours)
    df_per_ship = x4stats.get_df_per_ship(hours)
    trading = df_ships[df_ships['trades'] > 0]
    avg_profit = float(trading['value'].mean()) if len(trading) else 0.0

    return render_template(
        'ships.html',
        ship_count=len(df_ships),
        trading_count=len(trading),
        type_count=len(df_per_type),
        avg_profit=avg_profit,
        avg_profit_class=value_class(avg_profit),
        type_chart=get_bar_data(df_per_type.sort_values('profit_per_ship', ascending=False),
                                'ship_type_name', 'profit_per_ship'),
        ship_chart=get_bar_data(trading, 'ship_name', 'value'),
        type_columns=TABLE_COLUMNS_SHIP_TYPE,
        type_rows=df_per_type.to_dict('records'),
        ship_columns=TABLE_COLUMNS_SHIPS,
        ship_rows=df_ships.to_dict('records'),
        raw_columns=table_columns_ship(df_per_ship),
        raw_rows=df_per_ship.to_dict('records'),
        **hours_context(hours),
    )


# Events of the current game from the local history, newest first, limited to the look-back window
def get_loss_events(hours=None):
    game_time = x4stats.get_game_time()
    events = []
    for e in event_store.get_events(x4stats.get_game_guid()):
        hours_ago = math.floor((game_time - e['time']) / 3600)
        if hours and hours_ago > int(hours) - 1:
            continue
        events.append({**e, 'hours_ago': hours_ago, 'game_hours': e['time'] / 3600,
                       'what': 'Destroyed' if e['kind'] == 'destroyed' else 'Attacked'})
    return events


@app.route('/losses', methods=['GET'])
@app.route('/losses/<int:hours>', methods=['GET'])
def losses(hours=None):
    events = get_loss_events(hours)
    destroyed = [e for e in events if e['kind'] == 'destroyed']
    attacked = [e for e in events if e['kind'] == 'attacked']
    return render_template(
        'losses.html',
        destroyed_count=len(destroyed),
        attacked_count=len(attacked),
        last_loss=destroyed[0] if destroyed else None,
        telegram_on=notifier is not None,
        telegram_attacks=TELEGRAM_NOTIFY_ATTACKS,
        destroyed_columns=TABLE_COLUMNS_DESTROYED,
        destroyed_rows=destroyed,
        attacked_columns=TABLE_COLUMNS_ATTACKED,
        attacked_rows=attacked,
        **hours_context(hours),
    )


@app.route('/transactions', methods=['GET'])
@app.route('/transactions/<int:hours>', methods=['GET'])
def transactions(hours=None):
    df_sales = x4stats.get_df_sales_sorted(hours, filter_zero_value=True)
    return render_template(
        'transactions.html',
        transaction_columns=TABLE_COLUMNS_TRANSACTIONS,
        transaction_rows=df_sales.to_dict('records'),
        **hours_context(hours),
    )


# Re-check for a newer save, then go back to the page the link was clicked on (?next=<endpoint>)
# Polled by open pages to detect that a newer save was loaded in the background
@app.route('/api/save', methods=['GET'])
def save_status():
    return jsonify(version=x4stats.get_save_version())


@app.route('/reload', methods=['GET'])
@app.route('/reload/', methods=['GET'])
@app.route('/reload/<int:hours>', methods=['GET'])
def reload(hours=None):
    refresh_save()
    page = request.args.get('next')
    if page not in PAGES:
        page = 'stats'
    return redirect(url_for(page, hours=hours) if hours else url_for(page))


def port_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def main():
    global x4stats, event_store
    if port_in_use(HOST, PORT):
        print(f"Port {PORT} is already in use. Is X4stats already running? http://localhost:{PORT}/stats")
        sys.exit(1)

    event_store = EventStore(EVENTS_DB)
    # save ophalen
    x4stats = X4stats(
        save_location=save_location
    )
    sync_events()
    if AUTO_RELOAD_SECONDS:
        threading.Thread(target=poll_saves, args=(AUTO_RELOAD_SECONDS,), daemon=True).start()
        print(f" * Checking for new saves every {AUTO_RELOAD_SECONDS} seconds")
    print(" * Telegram notifications " + ("on" if notifier else "off"))
    app.run(host=HOST, port=PORT, threaded=True, debug=False)


if __name__ == '__main__':
    main()
