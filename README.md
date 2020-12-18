X4stats savegame trades analyser

This program is meant to read the X4 Foundations savegame (starting from version 4.00) and analyse the trade history of your ships and stations.

Features:  
-Graphs displaying trade value for ship, stations and their subordinates  
-Value of wares bought and sold  
-Profit margin calculation for traders  
-Adjustable timeframe for all of the above from 1 hour to all game time in 4.00

Planned features:  
-Listing of ships with trade or mining order which do not have any trades (inactive)  

Known issues and limitations:  
-Destroyed ships are no longer available in the save file. This means their trade value will no longer be displayed. In case the ship was a station subordinate, some of the stations profit will be lost eg:  
Ship buys e-cells for 10 and sells them to its commanding station for 12. If the subordinate ship is destroyed, only the station purchase for value 12 is kept in the save file. Meaning the trader's profit is lost. The same holds true for traders selling for stations.  
  
-Ships are displayed under their current commander taking all the previous trades with them. eg: Miner is mining on sector automine and makes 10k profit. Then it is assigned to as a station miner. The station will now shop 10k profit which it did not earn. 

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

copy or stats/config.example.py to stats/config.py  
copy a compressed savegame into the stats/saves folder  
edit the stats/config.py so that SAVEGAME_LOCATION reflects the savegame path  
  
run from the x4stats-main directory with  
```
x4stats
```
wait for the program to say the server is running and open  
http://localhost:2992/stats

Anytime you want to start the program you will first have to open the main directory in cmd.exe and run  
```
venv\Scripts\activate.bat && x4stats
```  

Preview:  
![preview image](https://github.com/harkovs/x4stats/blob/main/stats/static/images/example.png?raw=true)