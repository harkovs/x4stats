Windows:  
  
install python 3 64-bit  
https://www.python.org/downloads/windows/  
  
unpack  
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