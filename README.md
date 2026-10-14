X4stats savegame trades analyser

This program reads the X4 Foundations savegame (starting from version 4.00) and analyses the trade history of your ships and stations in a dashboard in your browser.

Features:  
-Overview of profit, sales, costs and margin, with the best wares and ships  
-Trends: profit per hour, per ware  
-Commanders: profit of stations and fleet commanders together with their subordinates, and per commander the wares traded and the ships in the group. Trades between your own ships and stations are not counted twice  
-Wares bought and sold, with sold and bought volume  
-Ships and ship types ranked by profit, profit per trade and per ship  
-Idle: ships with a trade or mining order that made no trades  
-Losses: destroyed ships and stations and ships that were attacked and forced to flee, with their type, commander and the orders they had at the time. Kept locally per game, so the history survives the game trimming its logbook  
-Optional Telegram alerts for new losses (and attacks)  
-Transactions: every trade of your ships and stations  
-Adjustable timeframe for all of the above from 1 hour to all game time  
-Picks up new saves automatically, open pages refresh when a newer save is loaded  

Known issues and limitations:  
-Destroyed ships are no longer available in the save file. This means their trade value will no longer be displayed. In case the ship was a station subordinate, some of the stations profit will be lost eg:  
Ship buys e-cells for 10 and sells them to its commanding station for 12. If the subordinate ship is destroyed, only the station purchase for value 12 is kept in the save file. Meaning the trader's profit is lost. The same holds true for traders selling for stations.  
  
-Ships are displayed under their current commander taking all the previous trades with them. eg: Miner is mining on sector automine and makes 10k profit. Then it is assigned to as a station miner. The station will now show 10k profit which it did not earn.  
-Ships are grouped under the top of their command chain (a wing of a ship that is assigned to a station counts for the station). Intermediate commanders are not shown as a separate level  
-Losses are read from the English logbook texts. With another game language they are not recognised  
-The commander and orders of a lost ship are those of the last save loaded before the loss. Losses recorded before this was added have none, unless the logbook entry is still in a save  

Installation instructions:  
Windows  
  
install python 3 64-bit  
https://www.python.org/downloads/windows/  
  
download and unpack x4stats from github  
open cmd.exe and enter the unpacked directory  
```
cd x4stats-main
python -m venv venv
venv\Scripts\activate.bat
pip install -e .
```

Linux  
```
cd x4stats
python -m venv venv
source venv/bin/activate
pip install -e .
```

Configuration:  
copy stats/config.example.py to stats/config.py  
edit stats/config.py so that SAVE_LOCATION is your save folder (the newest save in it is used) or a single savegame file  
eg. Windows `C:\Users\<your_username>\Documents\Egosoft\X4\<random_number>\save`, Linux `~/.config/EgoSoft/X4/<random_number>/save`  
the other settings in config.example.py are optional: how often to check for a new save, where the losses history is stored and Telegram alerts  
  
run from the x4stats directory with  
```
x4stats
```
wait for the program to say the server is running and open  
http://localhost:2992/stats

Anytime you want to start the program you will first have to open the main directory and run  
```
venv\Scripts\activate.bat && x4stats
```  
or on Linux  
```
source venv/bin/activate && x4stats
```  

While it runs, new saves are picked up every minute. "Update save" in the sidebar checks right away.  
Your losses history and the last known state of your ships are kept in stats/saves/events.sqlite. Delete it to start over.

Preview:  
![preview image](https://github.com/harkovs/x4stats/blob/main/stats/static/images/example.png?raw=true)
