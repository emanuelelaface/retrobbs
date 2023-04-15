#################################################################################################
# RetroBBS 0.20 (compatible with TURBO56K 0.6 and retroterm 0.14                              	#
#                                                                                           	#
# Coded by pastbytes and Durandal, from retrocomputacion.com                                  	#
#################################################################################################
#																								#
# October    7 - 2020:	Translation of console messages and code comments						#
# October    8 - 2020:	SendBitmap() code cleanup												#
# 					  	Function name translation 												#
#					  	Added _LOG() to replace most of the print calls							#
# October   12 - 2020:	Started config.ini implementation										#
# October   13 - 2020:	Added Slideshow()														#
# October   14 - 2020:	Slideshow() now can display .seq and .bin files							#
# October	15 - 2020:	Start cleanup of AudioList()											#
# 					  	Added PlayAudio()														#
#					  	First work into MenuStack implementation								#
#					  	Menu functions now return both the Menu Dictionary and a Parameters		#
#					  	Dictionary. Menu display functions must accept a Parameters Dictionary	#
#					  	as input parameter														#
#					  	While the Menu Dictionary provides the key binding->function pairing,	#
#					  	the Parameters Dictionary provides data that should survive in between	#
#					  	calls to the Menu display function										#
# October   16 - 2020:	ANSI colors on LOG messages												#
# November  25 - 2020:	Slideshow() accepts optional paramaters, delay time and waitkey boolean	#
#					  	opciones renamed valid_keys												#
#					  	old global variables cleanup											#
# November	26 - 2020:	More code cleanup, only one unused variable warning left at this point	#
#					  	Some advances in ConfigRead()											#
# November	27 - 2020:	Added SendRAWFile()														#
# November  29 - 2020:	Added waitkey parameter to SendRAWFile()								#
#						Fixed some menu handling in FileList(), AudioList and the main loop		#
#					  	Now you cant select a new file/picture/audio while displaying/playing	#
#					  	the current one															#
# November	30 - 2020:	Menudef dictionary entry now includes _waitkey status					#
#						entry = (_function,(parameters),_key,_showmenu,_waitkey)				#
#						ReceiveStr now checks if connection is active							#
#						Added cursor enable control												#
# December	 7 - 2020:	Initial SIDstream support												#
# December	 9 - 2020:	Added support for SID files to AudioList, uses HVSC .ssl files for		#
#						play length																#
# December	10 - 2020:	SIDStream() now supports abort from client side.						#
# December	19 - 2020:	Fixed bugs in AudioList() regarding file type detection					#
# February	21 - 2021:	SIDStream() protocol modified, more robust against net/modem latency	#
# February	22 - 2021:	SendBitmap() added lines parameter										#
# March		03 - 2021:	Further SIDStream protocol modifications								#
# March		04 - 2021:	Adapted to multiuser													#
# March		05 - 2021:	Text translation to English												#
# March		09 - 2021:	PlayAudio support for stream cancellation								#
# March		10 - 2021:	ImageDialog added, selection of HIRES/MULTI graphics modes				#
# March		11 - 2021:	ID3v2 TAG support for PCM audio info/AudioDialog added					#
# March		14 - 2021:	Advances in ConfigRead()												#
#						SendMenu() added, renders menus from MenuList structure					#
# March		15 - 2021:	SendText() added, renders txt through More() or seq CG petscii files	#
# March		16 - 2021:	SendCPetscii() and SendPETPetscii() added, support for .c and .pet files#
# March		17 - 2021:	Slideshow() support for PCM audio										#
# March		18 - 2021:	New menu system integrated to main bbs loop								#
# April		 3 - 2021:	WikiSearch() now shows the first image in the article (if any) before	#
# 						showing the article text.												#
# 						SendBitmap() now can accept an Image object or a ByteIO object as input	#
# April		 4 - 2021:	PlayAudio() checks if metadata is available before showing dialog		#
# April		 5 - 2021:	Version changed to 0.10													#
#						Implementation of plugin system and moving common routines to their own	#
#						modules/namespace														#
# April		 6 - 2021:	Starting modifications for fully OOP socket routines					#
# April		 7 - 2021:	Starting migration of file transfer functions to their own module		#
# April		 7 - 2021:	ShowYT moved to its own plugin											#
# April		 7 - 2021:	WikiSearch moved to its own plugin										#
# Late 2021-May 2022 :  Audio functions moved to their own module, started database handling,   #
#                       user login, etc.                                                        #
#                       MenuDef index 3 now stores the minimun user class needed to access menu #
#################################################################################################


from __future__ import print_function

import argparse
import time
import socket
import sys
import re
import platform
import subprocess
from os import walk
from os.path import splitext, getmtime, basename
import datetime
import signal
import string
import itertools
import configparser #INI file parser
import threading

#Petscii
import common.petscii as P
#Encoders
import common.extensions as EX

#Turbo56K
from common import turbo56k as TT

from common.classes import BBS
from common.connection import Connection
from common.bbsdebug import _LOG, bcolors, set_verbosity
from common.helpers import MenuBack, valid_keys, formatX, More, SetPage, crop, format_bytes
from common.style import KeyPrompt, bbsstyle, default_style, RenderMenuTitle, KeyLabel
from common import audio as AA
from common import messaging as MM
from common import video as VV

#File transfer functions
import common.filetools as FT

# import importlib
# import pkgutil


#Import plugins ******************************
#import plugins

# def iter_namespace(ns_pkg):
#     # Specifying the second argument (prefix) to iter_modules makes the
#     # returned name an absolute name instead of a relative one. This allows
#     # import_module to work without having to do additional modification to
#     # the name.
#     return pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + ".")


##################################
# BBS Version                    #
_version = 0.25                  #
##################################


#Threads running flag
_run = True

#Timeout default value (secs)
_tout = 60.0*5


#Configuration file
config_file = 'config.ini'

#Plugins dictionary
#PlugDict = {}

#Reads Config file
def ConfigRead():
    global bbs_instance

    #Iterate Section Entries
    def EIter(cfg, key, sentry):
        PlugDict = bbs_instance.plugins
        nchar = 0   # LABEL (no associated key) entries use chars 0x00 to 0x0c
        for e in range(0,sentry['entries']):
            tentry = cfg[key]['entry'+str(e+1)+'title']	#Entry Title
            if sentry['columns'] < 2:
                dentry = cfg.get(key,'entry'+str(e+1)+'desc', fallback = '')
                if dentry != '':
                    tentry = (tentry,dentry)
            efunc = cfg.get(key,'entry'+str(e+1)+'func', fallback ='LABEL')		#Entry Internal function
            if efunc != 'LABEL':
                try:
                    ekey = bytes(cfg[key]['entry'+str(e+1)+'key'],'ascii')		#Entry Key binding
                except:
                    raise Exception('Configuration file - Menu entry missing associated key')
            else:
                ekey = bytes(chr(nchar),'ascii')
                nchar += 1
                if nchar == '\r':
                    raise Exception('Configuration file - Too many LABEL entries')
            level = cfg.getint(key,'entry'+str(e+1)+'level', fallback = 0)
            if efunc in func_dic:
                #[function_call, parameters, title, ???, wait]
                sentry['entrydefs'][ekey] = [func_dic[efunc],None,tentry,level,False]
            elif efunc in PlugDict:
                sentry['entrydefs'][ekey] = [PlugDict[efunc][0],None,tentry,level,False]
            else:
                raise Exception('Configuration file - Unknown function at: '+'entry'+str(e+1)+'func')
            #Parse parameters
            parms = []
            if efunc == 'IMAGEGALLERY':		#Show image file list
                p = cfg.get(key, 'entry'+str(e+1)+'path', fallback='images/')
                parms= [tentry,'','Displaying image list',p,('.art','.ocp','.koa','.kla','.dd','.ddl','.ART','.OCP','.KOA','.KLA','.DD','.DDL','.gif','jpg','png','.GIF','.JPG','PNG'),FT.SendBitmap,cfg.getboolean(key,'entry'+str(e+1)+'save',fallback=False)]
            elif efunc == 'SWITCHMENU':		#Switch menu
                parms = [cfg[key].getint('entry'+str(e+1)+'id')]
            elif efunc == 'FILES':			#Show file list
                te = cfg.get(key,'entry'+str(e+1)+'ext', fallback='')
                if te != '':
                    exts = tuple(te.split(','))
                else:
                    exts = ()
                p = cfg.get(key, 'entry'+str(e+1)+'path', fallback='programs/')
                parms = [tentry,'','Displaying file list',p,exts,FT.SendFile,cfg.getboolean(key,'entry'+str(e+1)+'save',fallback=False)]
            elif efunc == 'AUDIOLIBRARY':	#Show audio file list
                p = cfg.get(key, 'entry'+str(e+1)+'path', fallback='sound/')
                parms = [tentry,'','Displaying audio list',p]
            elif efunc == 'PCMPLAY':		#Play PCM audio
                parms = [cfg.get(key, 'entry'+str(e+1)+'path', fallback=bbs_instance.Paths['bbsfiles']+'bbsintroaudio-eng11K8b.wav'),None]
            elif efunc == 'GRABFRAME':		#Grab video frame
                parms = [cfg.get(key, 'entry'+str(e+1)+'path', fallback=''),None]
            elif efunc == 'SIDPLAY':        #Play SID/MUS
                parms = [cfg.get(key, 'entry'+str(e+1)+'path', fallback = ''),cfg.getint(key,'entry'+str(e+1)+'playt',fallback=None),False,cfg.getint(key,'entry'+str(e+1)+'subt',fallback=None)]
            elif efunc == 'SLIDESHOW':		#Iterate through and show all supported files in a directory
                parms = [tentry,cfg.get(key, 'entry'+str(e+1)+'path', fallback=bbs_instance.Paths['bbsfiles']+'pictures')]
            elif efunc == 'INBOX':
                parms = [0]
            elif efunc == 'BOARD':
                parms = [cfg.getint(key,'entry'+str(e+1)+'id', fallback = 1)]
            # functions without parameters
            elif efunc in ['BACK','EXIT','USEREDIT','USERLIST','MESSAGE','LABEL','STATS']:
                parms = []
            elif efunc in PlugDict:			#Plugin function
                parms = []
                for p in PlugDict[efunc][1]:	#Iterate parameters
                    ep = cfg.get(key, 'entry'+str(e+1)+p[0], fallback=p[1])
                    if isinstance(p[1],tuple) == True and isinstance(ep,tuple) == False:
                        ep = tuple([int(e) if e.isdigit() else 0 for e in ep.split(',')])
                    parms.append(ep)

            # This tuple need to be added to one (conn,) on each connection instance when calling func
            # also needs conn.MenuParameters added to this
            # finaltuple = (conn,)+ _parms_
            sentry['entrydefs'][ekey][1] = tuple(parms)
        return(sentry)


    #Iterate Menu Sections
    def MIter(cfg, key, mentry):
        for s in range(0, mentry['sections']):
            skey = key+str(s+1)
            tsection = cfg[skey]['title']						#Section Title
            ecount = cfg[skey].getint('entries')				#Section number of entries
            scolumns = cfg[skey].getint('columns', fallback= 2)
            mentry['entries'][s] = {'title':tsection,'entries':ecount,'columns':scolumns,'entrydefs':{}}
            mentry['entries'][s] = EIter(cfg, skey, mentry['entries'][s])
        return(mentry)
    
    #Internal function dictionary
    func_dic = {'IMAGEGALLERY': FileList,
                'AUDIOLIBRARY': AA.AudioList,
                'FILES': FileList,
                'SENDRAW': FT.SendRAWFile,
                'SWITCHMENU': SwitchMenu,
                'SLIDESHOW': SlideShow,
                'SIDPLAY': AA.SIDStream,
                'CHIPPLAY': AA.CHIPStream,
                'PCMPLAY': AA.PlayAudio,
                'TEXT': FT.SendText,
                'SHOWPIC': FT.SendBitmap,
                'EXIT': LogOff,
                'BACK': MenuBack,
                'USEREDIT': EditUser,
                'USERLIST': UserList,
                'BOARD': MM.inbox,
                'INBOX': MM.inbox,
                'GRABFRAME': VV.Grabframe,
                'STATS': Stats,
                'LABEL': None}

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config.read(config_file)

    bbs_instance.cfgmts = getmtime(config_file) # Set latest configuration file modify datestamp

    #MAIN variables

    bbs_instance.name = config['MAIN']['bbsname']
    bbs_instance.ip = config['MAIN']['ip']
    bbs_instance.port = config['MAIN'].getint('port')
    bbs_instance.lines = config['MAIN'].getint('lines', fallback= 5)
    bbs_instance.lang = config['MAIN']['language']
    bbs_instance.WMess = config['MAIN'].get('welcome', fallback='Welcome!')
    bbs_instance.GBMess = config['MAIN'].get('goodbye', fallback='Goodbye!')
    bbs_instance.BSYMess = config['MAIN'].get('busy', fallback='BUSY')

    bbs_instance.dateformat = config['MAIN'].getint('dateformat', fallback=1)

    #Get any paths
    try:
        bbs_instance.Paths = dict(config.items('PATHS'))
    except:
        bbs_instance.Paths = {'temp':'tmp/','bbsfiles':'bbsfiles/'}
    #Get any message boards options
    try:
        bbs_instance.BoardOptions = dict(config.items('BOARDS'))
    except:
        bbs_instance.BoardOptions = {}
    #Get any plugin config options
    try:
        bbs_instance.PlugOptions = dict(config.items('PLUGINS'))
    except:
        bbs_instance.PlugOptions = {}


    #Parse Menues
    mcount = config['MAIN'].getint('menues')								#Number of menues

    _bbs_menues = [None] * mcount

    for m in range(0, mcount):		#Iterate menues
        if m == 0:
            tmenu = config['MAINMENU']['title']								#MainMenu title
            scount = config['MAINMENU'].getint('sections')					#MainMenu number of sections
            tkey = 'MAINMENUSECTION'
            prompt = config['MAINMENU'].get('prompt', fallback='sELECTION:')
        else:
            tmenu = config['MENU'+str(m+1)]['title']						#Menu title
            scount = config['MENU'+str(m+1)].getint('sections')				#Menu number of sections
            prompt = config['MENU'+str(m+1)].get('prompt', fallback='sELECTION:')
            tkey = 'MENU'+str(m+1)+'SECTION'

        _bbs_menues[m] = {'title':tmenu, 'sections':scount, 'prompt':prompt, 'type':0, 'entries':[{}]*scount}
        _bbs_menues[m] = MIter(config,tkey,_bbs_menues[m])
        _bbs_menues[m]['entries'][0]['entrydefs'][b'\r']=[SendMenu,(),'',False,False]

    bbs_instance.MenuList = _bbs_menues

#Handles CTRL-C
def signal_handler(sig, frame):
    global _run
    global conlist
    global conthread
    global bbs_instance

    _LOG('Ctrl+C! Bye!', v=3)
    _run = False

    for t in range(1,bbs_instance.lines+1):
        if t in conlist:				#Find closed connections
            conlist[t][0].join()
    conthread.join()

    try:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
    except:
        pass
    del bbs_instance
    sys.exit(0)


def FileList(conn:Connection,title,speech,logtext,path,ffilter,fhandler,transfer=False):

    if conn.menu != -1:
        conn.MenuStack.append([conn.MenuDefs,conn.menu])
        conn.menu = -1
    # Init Menu parameter dictionary if needed
    if conn.MenuParameters == {}:
        conn.MenuParameters['current'] = 0

    transfer &= conn.QueryFeature(TT.FILETR) < 0x80

    # Start with barebones MenuDic
    MenuDic = { 
                b'_': (MenuBack,(conn,),"Previous Menu",0,False),
                b'\r': (FileList,(conn,title,speech,logtext,path,ffilter,fhandler,transfer),title,0,False)
              }	


    _LOG(logtext,id=conn.id, v=4)
    # Send speech message
    conn.Sendall(TT.to_Speech() + speech)
    time.sleep(1)
    # Select screen output
    conn.Sendall(TT.to_Screen())
    # Sync
    conn.Sendall(chr(0)*2)
    # # Text mode
    conn.Sendall(TT.to_Text(0,0,0))

    RenderMenuTitle(conn,title)

    # Send menu options
    files = []	#all files
    programs = []	#filtered list
    #Read all files from 'path'
    for entries in walk(path):
        files.extend(entries[2])
        break

    #Filter out all files not matching 'filter'
    if len(ffilter) > 0:
        for f in files:
            if f.endswith(ffilter):
                programs.append(f)
    else:
        programs = files

    programs.sort()	#Sort list

    pages = int((len(programs)-1) / 40) + 1
    count = len(programs)
    start = conn.MenuParameters['current'] * 40
    end = start + 39
    if end >= count:
        end = count - 1

    #Add pagination keybindings to MenuDic
    if pages > 1:
        if conn.MenuParameters['current'] == 0:
            page = pages-1
        else:
            page = conn.MenuParameters['current']-1
        MenuDic[b'<'] = (SetPage,(conn,page),'Previous Page',0,False)
        if conn.MenuParameters['current'] == pages-1:
            page = 0
        else:
            page = conn.MenuParameters['current']+1
        MenuDic[b'>'] = (SetPage,(conn,page),'Next Page',0,False)

    if fhandler == FT.SendFile:
        keywait = False
    else:
        keywait = True

    x = 0

    for x in range(start, end + 1):
        if x % 4 == 0 or x % 4 == 1:
            color1 = P.LT_BLUE
            color2 = P.GREY3
        if x % 4 == 2 or x % 4 == 3:
            color1 = P.CYAN
            color2 = P.YELLOW
        if len(ffilter) == 0:
            if len(programs[x]) > 16:
                fn = splitext(programs[x])
                label = fn[0][:16-len(fn[1])]+fn[1]
            else:
                label = programs[x]
        else:
            label = splitext(programs[x])[0]
        KeyLabel(conn, valid_keys[x-start], (label+' '*16)[:16]+(''if x%2 else '  '), (x % 4)<2)
        #Add keybinding to MenuDic
        if fhandler == FT.SendFile:
            parameters = (conn,path+programs[x],True,transfer,)
        else:
            parameters = (conn,path+programs[x],True,transfer,)
        MenuDic[valid_keys[x-start].encode('ascii','ignore')] = (fhandler,parameters,valid_keys[x-start],0,keywait)

    conn.SendTML(f'<AT x=1 y=23><GREY3><RVSON><LARROW> <LTGREEN>Prev. Menu <GREY3>&lt; <LTGREEN>Prev.Page <GREY3>&gt; <LTGREEN>Next Page  <RVSOFF><BR>'
                f'<WHITE> [{conn.MenuParameters["current"]+1}/{pages}]<CYAN> Selection:<WHITE> ')
    conn.Sendall(chr(255) + chr(161) + 'seleksioneunaopsion,')
    time.sleep(1)
    # Select screen output
    conn.Sendall(TT.to_Screen())
    return MenuDic

#################################################
# Render Menu from MenuList structure           #
#################################################
def SendMenu(conn:Connection):

    if conn.menu < 0:
        return()
    conn.Sendall(TT.to_Text(0,0,0)+TT.to_Screen())	#Set Screen Text mode output
    tmenu = conn.bbs.MenuList[conn.menu]	#Change to simply tmenu = conn.MenuDefs
    _LOG("Sending menu: "+tmenu['title'],id=conn.id,v=4)
    RenderMenuTitle(conn,tmenu['title'])
    conn.Sendall('\r')
    for scount, s in enumerate(tmenu['entries']):
        #Sections
        if len(s['title'])>0 or scount > 0:
            conn.Sendall(' '+chr(P.WHITE)+P.toPETSCII(s['title'])+'\r')
        conn.Sendall(chr(P.LT_GREEN)+chr(176)+38*chr(P.HLINE)+chr(174))

        #Items
        count = 0
        toggle = False
        if s['columns'] < 2:
            sw = 1
            tw = 37
        else:
            sw = 2
            tw = 17
        for i in s['entrydefs']:
            if i == b'\r':
                continue

            xw = (2 if i<b'\r' else 0)    # Extra width if LABEL item

            if isinstance(s['entrydefs'][i][2],tuple):
                t = s['entrydefs'][i][2][0]
                dw = 38 if len(t) == 0 and i<b'\r' else 36
                desc = formatX(s['entrydefs'][i][2][1],columns=dw)
            else:
                t = s['entrydefs'][i][2]
                desc =''

            title = crop(t,tw+xw-1)   #t if len(t)<(tw+xw) else t[0:(tw+xw)-4]+'...'

            if len(title) > 0 or count > (sw-1) or i >= b'\r':
                if i < b'\r' and count % sw == 0:    #NULL entry
                        conn.Sendall(chr(P.LT_GREEN)+chr(P.VLINE))
                KeyLabel(conn,chr(i[0]),title, toggle)
                #if i < b'\r' and count % sw != 0:
                #    conn.Sendall(' ')

                if count % sw == 0:
                    toggle = not toggle
                    line = ' '*((tw+xw)-1-len(title))+(' 'if sw == 2 else chr(P.GREEN)+chr(P.VLINE))
                    conn.Sendall(line)
                else:
                    conn.Sendall(' '*(19-(len(title)+(3-int(xw*1.5))))+chr(P.GREEN)+chr(P.VLINE))
            if desc != '':
                tdesc = ''
                for l in desc:
                    tdesc += chr(P.LT_GREEN)+chr(P.VLINE)+chr(P.WHITE)+(' '*(38-dw))+l+((dw-len(l))*' ')+chr(P.GREEN)+chr(P.VLINE)
                conn.Sendall(tdesc)
            count += 1
        if (count % sw == 1) and (sw == 2):
            conn.Sendall(' '*19+chr(P.GREEN)+chr(P.VLINE))


        conn.Sendall(chr(173)+38*chr(P.HLINE)+chr(189))
    ####
    conn.Sendall(TT.set_CRSR(0,24)+chr(P.WHITE)+' '+P.toPETSCII(tmenu['prompt'])+' ')
    #WaitRETURN(conn)



# Display sequentially all matching files inside a directory
def SlideShow(conn:Connection,title,path,delay = 1, waitkey = True):
    # Sends menu options
    files = []	#all files
    slides = []	#filtered list
    #Read all the files from 'path'
    for entries in walk(path):
        files.extend(entries[2])
        break

    pics_e = ('.ART','.OCP','.KOA','.KLA','.GIF','.JPG','PNG')
    text_e = ('.TXT','.SEQ')
    bin_e = ('.BIN','.raw')
    pet_e = ('.C','.PET')
    aud_e = ('.MP3','.WAV')
    chip_e = ('.SID','.MUS','.YM','.VTX','.VGZ')

    #Keeps only the files with matching extension 
    for f in files:
        if f.upper().endswith(pics_e + text_e + bin_e + pet_e + aud_e + chip_e):
            slides.append(f)

    slides.sort()	#Sort list

    #Iterate through files
    for p in slides:
        w = 0
        conn.Sendall(TT.enable_CRSR()+chr(P.CLEAR))
        _LOG('SlideShow - Showing: '+p,id=conn.id,v=4)
        ext = splitext(p)[1].upper()
        if ext in pics_e:
            FT.SendBitmap(conn, path+p)
        elif ext in bin_e:
            slide = open(path+p,"rb")
            binary = slide.read()
            slide.close()
            conn.Sendallbin(binary)
        elif ext in text_e:
            w = FT.SendText(conn,path+p,title)
        elif ext in pet_e[0:2]:
            w = FT.SendCPetscii(conn,path+p,(0 if waitkey else delay))
        elif ext in pet_e[2:4]:
            w = FT.SendPETPetscii(conn,path+p)
        elif (ext in aud_e) and (conn.QueryFeature(TT.STREAM) < 0x80):
            AA.PlayAudio(conn,path+p,None)
            w = 1
        elif (ext in chip_e) and (conn.QueryFeature(TT.SIDSTREAM) < 0x80):
            AA.CHIPStream(conn,path+p,None,False)
            w = 1
        else:   # Dont wait for RETURN if file is not supported
            w = 1
        # Wait for the user to press RETURN
        if waitkey == True and w == 0:
            WaitRETURN(conn,60.0*5)
        else:
            time.sleep(delay)

        conn.Sendall(TT.to_Text(0,0,0))
    conn.Sendall(TT.enable_CRSR())

def WaitRETURN(conn:Connection,timeout = 60.0):
    # Wait for user to press RETURN
    _LOG('Waiting for the user to press RETURN...',id=conn.id,v=4)
    tecla = b''
    conn.socket.settimeout(timeout)
    while conn.connected == True and tecla != b'\r':
        tecla = conn.Receive(1)
        if tecla == b'':
            conn.connected = False
    conn.socket.settimeout(_tout)
    if conn.connected == False:
        try:
            conn.socket.sendall(b'tIMEOUT - dESCONECTADO ')
        except socket.error:
            pass
    _LOG(bcolors.OKBLUE+str(tecla)+bcolors.ENDC,id=conn.id,v=4)

def WaitKey(conn:Connection):
    # Wait for the user to press any key
    _LOG('Waiting for the user to press a key...',id=conn.id,v=4)
    tecla = b''
    conn.socket.settimeout(60.0)
    tecla = conn.Receive(1)
    if tecla == b'':
        conn.connected = False
        try:
            conn.socket.sendall(b'tIMEOUT - dESCONECTADO ')
        except socket.error:
            pass
    conn.socket.settimeout(_tout)

# Logoff
def LogOff(conn:Connection, confirmation=True):

    lan = {'en':['aRE YOU SURE (y/n)? ','YN','dISCONNECTED'],'es':['eSTA SEGURO (s/n)? ','SN','dESCONECTADO']}

    l_str = lan.get(conn.bbs.lang,lan['en'])

    if confirmation == True:
        conn.Sendall(chr(P.DELETE)*23 + chr(P.LT_GREEN) + l_str[0] + chr(P.WHITE))
        time.sleep(1)
        data = ''
        #while data != b'Y' and data != b'N':
        #	data = conn.Receive(1)
        data = conn.ReceiveKey(bytes(l_str[1],'ascii'))
        if data == bytes(l_str[1][0],'ascii'):
            _LOG('Disconnecting...\r',id=conn.id,v=3)
            conn.Sendallbin(data)
            time.sleep(1)
            conn.Sendall(chr(P.WHITE) + '\r\r'+P.toPETSCII(conn.bbs.GBMess)+'\r')
            time.sleep(1)
            conn.Sendall(chr(P.LT_BLUE) + '\r'+l_str[2]+'\r'+chr(P.WHITE))
            time.sleep(1)
            conn.connected = False	#break
            return True
        else:
            return False
    else:
        conn.connected = False
        return True


# Switch menu
def SwitchMenu(conn:Connection, id):
    if id-1 != conn.menu:
        if len(conn.MenuDefs) != 0:
            conn.MenuStack.append([conn.MenuDefs,conn.menu])
        conn.menu = id-1
        conn.MenuDefs = GetKeybindings(conn,id-1)
        #Function = conn.MenuDefs[b'\r'][0]
        #Function(*conn.MenuDefs[b'\r'][1])

        #conn.newmenu = id-1	#replace

# Generate keybindings
def GetKeybindings(conn:Connection,id):

    menu = conn.bbs.MenuList[id]
    kb = {}
    for cat in menu['entries']:
        #kb.update(cat['entrydefs'])
        for e in cat['entrydefs']:
            kb[e] = cat['entrydefs'][e].copy()
            if isinstance(kb[e][2],tuple):
                kb[e][2]=kb[e][2][0]
            kb[e][1] = (conn,)+kb[e][1]
    return kb

# Show BBS/User statistics
def Stats(conn:Connection):
    _LOG("Displaying stats",v=4,id=conn.id)
    conn.Sendall(TT.split_Screen(0,False,0,0)) # Cancel any split screen/window
    RenderMenuTitle(conn,"BBS Stats")
    conn.Sendall(TT.set_Window(3,24))
    bstats = conn.bbs.database.bbsStats()
    if bstats != None:
        utime = bstats.get('uptime',0)
        visits = bstats.get('visits',1)
        latest = bstats.get('latest',conn.username)
    else:
        utime = 0
        visits = 1
        latest = [conn.username]
    tt = utime + (time.time() - conn.bbs.runtime)
    text = '\r'+chr(P.CYAN)+P.toPETSCII('BBS Session uptime: ')+chr(P.WHITE)+str(datetime.timedelta(seconds=round(time.time() - conn.bbs.runtime)))+'\r'
    text += chr(P.CYAN)+P.toPETSCII('BBS Total uptime: ')+chr(P.WHITE)+str(datetime.timedelta(seconds=round(tt)))+'\r'
    text += chr(P.CYAN)+P.toPETSCII('Total visits to the BBS: ')+chr(P.WHITE)+str(visits)+'\r'
    text += chr(P.CYAN)+P.toPETSCII('Registered users: ')+chr(P.WHITE)+str(len(conn.bbs.database.getUsers()))+'\r'
    text += '\r'+chr(P.CYAN)+P.toPETSCII('Last 10 visitors:\r\r')
    for i,l in enumerate(latest):
        text += chr(P.YELLOW)+chr(P.RVS_ON)+chr(181)+str(i)+chr(182)+chr(P.RVS_OFF)+chr(P.WHITE)+P.toPETSCII(l)+'\r'
    text += chr(P.YELLOW)+chr(P.HLINE)*40
    text += chr(P.LT_GREEN)+P.toPETSCII('Your Stats:\r\r')
    text += chr(P.CYAN)+P.toPETSCII('This session time: ')+chr(P.WHITE)+str(datetime.timedelta(seconds= round(time.time() - conn.stime)))+'\r'
    text += chr(P.CYAN)+P.toPETSCII('Session Upload/Download: ')+chr(P.WHITE)+P.toPETSCII(format_bytes(conn.inbytes))+chr(P.YELLOW)+'/'+chr(P.WHITE)+P.toPETSCII(format_bytes(conn.outbytes))+'\r'
    if conn.userclass > 0:
        udata = conn.bbs.database.chkUser(conn.username)
        tt = udata.get('totaltime',0) + (time.time() - conn.stime)
        tup  = format_bytes(udata.get('upbytes',0) + conn.inbytes)
        tdwn = format_bytes(udata.get('downbytes',0) + conn.outbytes)
        text += chr(P.CYAN)+P.toPETSCII('Total session time: ')+chr(P.WHITE)+str(datetime.timedelta(seconds=round(tt)))+'\r'
        text += chr(P.CYAN)+P.toPETSCII('Total Upload/Download: ')+chr(P.WHITE)+P.toPETSCII(tup)+chr(P.YELLOW)+'/'+chr(P.WHITE)+P.toPETSCII(tdwn)+'\r'
    
    More(conn,text,22)
    conn.Sendall(TT.set_Window(0,24))

# SignIn/SignUp
def SignIn(conn:Connection):

    # dateord = [[0,1,2],[1,0,2],[2,1,0]]
    # dateleft = [[0,3,3],[3,0,3],[3,5,0]]

    keys = string.ascii_letters + string.digits + ' +-_,.$%&'
    #conn.Sendall(chr(P.CLEAR)+chr(P.CYAN)+'uSERNAME:')
    conn.SendTML('<CLR><CYAN>Username:')
    Done = False
    while not Done:
        name = conn.ReceiveStr(bytes(keys,'ascii'), 16, False)
        if not conn.connected:
            return
        while len(name) > 0 and len(name) < 6:
            #conn.Sendall('\ruSERNAME MUST BE 6 TO 16 CHARACTERS\rLONG, TRY AGAIN:')
            conn.SendTML('<BR>Username must be 6 to 16 characters<BR>long, try again:')
            name = conn.ReceiveStr(bytes(keys,'ascii'), 16, False)
            if not conn.connected:
                return
        #name = P.toASCII(name)
        if len(name) > 0 and P.toASCII(name) != '_guest_':
            uentry = conn.bbs.database.chkUser(P.toASCII(name))
            if uentry != None:
                retries = 3
                if uentry['online'] == 1:
                    Done = True
                    #conn.Sendall('\ruSER ALREADY LOGGED IN\r')
                    conn.SendTML('<BR>User already logged in<BR>>')
                while (not Done) and (retries > 0):
                    #conn.Sendall('\rpASSWORD:')
                    conn.SendTML('<BR>Password:')
                    if conn.bbs.database.chkPW(uentry, P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16, True))):
                        #conn.Sendall(chr(P.LT_GREEN)+'\rlOGIN SUCCESSFUL'+chr(7)+chr(P.CHECKMARK))
                        conn.SendTML('<LTGREEN><BR>Login successful<BELL><CHECKMARK><PAUSE n=1')
                        conn.username = P.toASCII(name)
                        conn.userid = uentry.doc_id
                        conn.userclass = uentry['uclass']
                        #time.sleep(1)
                        Done = True
                    else:
                        retries -= 1
                        #conn.Sendall(chr(P.RED)+'\rpASSWORD INCORRECT'+chr(P.CYAN))
                        conn.SendTML('<RED><BR>Password incorrect<CYAN><PAUSE n=1')
                        #time.sleep(1)
                if retries == 0:
                    Done = True
                if not conn.connected:
                    return
            else:
                #conn.Sendall('\ruSER NOT FOUND, REGISTER (y/n)?')
                conn.Sendall('<BR>User not found, reguster (Y/N)?')
                if conn.ReceiveKey(b'YN') == b'Y':
                    # dord = dateord[conn.bbs.dateformat]
                    # dleft = dateleft[conn.bbs.dateformat]
                    if conn.bbs.dateformat == 1:
                        datestr = "%m/%d/%Y"
                        dout = "mm/dd/yyyy"
                    elif conn.bbs.dateformat == 2:
                        datestr = "%Y/%m/%d"
                        dout = "yyyy/mm/dd"
                    else:
                        datestr = "%d/%m/%Y"
                        dout = "dd/mm/yyyy"
                    if not conn.connected:
                        return
                    if conn.QueryFeature(179) < 0x80:
                        lines = 13
                    else:
                        lines = 25
                    FT.SendText(conn,conn.bbs.Paths['bbsfiles']+'terms/rules.txt','',lines)
                    #conn.Sendall('\rrEGISTERING USER '+name+'\riNSERT YOUR PASSWORD:')
                    conn.SendTML(f'<BR>Registering user {name}<BR>Insert your password:')
                    pw = conn.ReceiveStr(bytes(keys,'ascii'), 16, True)
                    if not conn.connected:
                        return
                    while len(pw) < 6:
                        #conn.Sendall('\rpASSWORD MUST BE 6 TO 16 CHARACTERS LONGiNSERT YOUR PASSWORD:')
                        conn.SendTML('<BR>Password must be 6 to 16 characters long<BR>Insert your password:')
                        pw = conn.ReceiveStr(bytes(keys,'ascii'), 16, True)
                        if not conn.connected:
                            return
                    #conn.Sendall('\rfIRST NAME:')
                    conn.SendTML('<BR>First name:')
                    fname = conn.ReceiveStr(bytes(keys,'ascii'), 16)
                    if not conn.connected:
                        return
                    #conn.Sendall('\rlAST NAME:')
                    conn.SendTML('<BR>Last name:')
                    lname = conn.ReceiveStr(bytes(keys,'ascii'), 16)
                    if not conn.connected:
                        return
                    #conn.Sendall('\rcOUNTRY:')
                    conn.SendTML('<BR>Country')
                    country = conn.ReceiveStr(bytes(keys,'ascii'), 16)
                    if not conn.connected:
                        return
                    bday = conn.ReceiveDate('\rbIRTHDATE: ',datetime.date(1900,1,1),datetime.date.today(),datetime.date(1970,1,1))
                    conn.username = P.toASCII(name)
                    conn.userid = conn.bbs.database.newUser(P.toASCII(name), P.toASCII(pw), P.toASCII(fname), P.toASCII(lname), bday.strftime("%d/%m/%Y"), P.toASCII(country))
                    _LOG('NEW USER: '+name,v=3)
                    conn.userclass = 1
                    #conn.Sendall('\rrEGISTRATION COMPLETE, WELCOME!')
                    conn.SendTML(f'<BR>Registration complete, welcome!<PAUSE n=1>'
                                f'<YELLOW><BR>Your user data:<BR><GREEN><HLINE n=14><BR>'
                                f'<ORANGE>User name: <WHITE>{name}<BR>'
                                f'<ORANGE>Password: <WHITE>{"*"*len(pw)}<BR>'
                                f'<ORANGE>First name: <WHITE>{fname}<BR>'
                                f'<ORANGE>Last name: <WHITE>{lname}<BR>'
                                f'<ORANGE>Birthdate: <WHITE>{bday.strftime(datestr)}<BR>'
                                f'<ORANGE>Country: <WHITE>{country}<BR><PAUSE n=1>'
                                f'<BR><YELLOW>Do you want to edit your data (Y/N)?')
                    #Done = True
                    #time.sleep(1)
                    # conn.Sendall(chr(P.YELLOW)+'\ryOUR USER DATA:\r'+chr(P.GREEN)+chr(P.HLINE)*14+'\r')
                    # conn.Sendall(chr(P.ORANGE)+'uSER NAME: '+chr(P.WHITE)+name+'\r')
                    # conn.Sendall(chr(P.ORANGE)+'pASSWORD: '+chr(P.WHITE)+('*'*len(pw))+'\r')
                    # conn.Sendall(chr(P.ORANGE)+'fIRST NAME: '+chr(P.WHITE)+fname+'\r')
                    # conn.Sendall(chr(P.ORANGE)+'lAST NAME: '+chr(P.WHITE)+lname+'\r')
                    # conn.Sendall(chr(P.ORANGE)+'bIRTHDATE '+chr(P.WHITE)+bday.strftime(datestr)+'\r')
                    # conn.Sendall(chr(P.ORANGE)+'cOUNTRY: '+chr(P.WHITE)+country+'\r')
                    # time.sleep(1)
                    # conn.Sendall('\r'+chr(P.YELLOW)+"dO YOU WANT TO EDIT YOUR DATA (y/n)?")
                    if conn.ReceiveKey(b'YN') == b'Y':
                        if not conn.connected:
                            return
                        #Edit user data
                        EditUser(conn)
                else:
                    Done = True
                if not conn.connected:
                    return
        else:
            Done = True
#

# Edit logged in user
# This always runs outside the mainloop regardless of where is called
def EditUser(conn:Connection):
    _LOG('Editing user '+conn.username, v=3)
    keys = string.ascii_letters + string.digits + ' +-_,.$%&'
    if conn.bbs.dateformat == 1:
        datestr = "%m/%d/%Y"
        dout = "mm/dd/yyyy"
    elif conn.bbs.dateformat == 2:
        datestr = "%Y/%m/%d"
        dout = "yyyy/mm/dd"
    else:
        datestr = "%d/%m/%Y"
        dout = "dd/mm/yyyy"
    if conn.userid == 0:
        return
    conn.Sendall(TT.split_Screen(0,False,0,0)) # Cancel any split screen/window
    done = False
    while (not done) and conn.connected:
        uentry = conn.bbs.database.chkUser(conn.username)
        RenderMenuTitle(conn,"Edit User Data")
        conn.Sendall(chr(P.CRSR_DOWN)*2)
        KeyLabel(conn,'a','Username: '+uentry['uname'],True)
        conn.Sendall('\r')
        KeyLabel(conn,'b','First name: '+uentry['fname'],False)
        conn.Sendall('\r')
        KeyLabel(conn,'c','Last name: '+uentry['lname'],True)
        conn.Sendall('\r')
        KeyLabel(conn,'d','Birthdate: '+datetime.datetime.strptime(uentry['bday'],'%d/%m/%Y').strftime(datestr),False)
        conn.Sendall('\r')
        KeyLabel(conn,'e','Country: '+uentry['country'],True)
        conn.Sendall('\r')
        KeyLabel(conn,'f','Change password',False)
        conn.Sendall('\r')
        KeyLabel(conn,'_','Exit',True)
        conn.Sendall('\r\r')
        if conn.QueryFeature(TT.LINE_FILL) < 0x80:
            conn.Sendall(TT.Fill_Line(12,64))
        else:
            conn.Sendall(chr(P.CRSR_UP)+(chr(P.HLINE)*40))
        conn.Sendall('pRESS OPTION')
        k = conn.ReceiveKey(b'ABCDEF_')
        if k == b'_':
            done = True
        elif k == b'A': #Username
            n = False
            conn.Sendall('\r'+chr(P.CRSR_UP))
            while not n:
                if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                    conn.Sendall(TT.Fill_Line(13,32))
                else:
                    conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP))
                conn.Sendall(chr(P.YELLOW)+'nEW USERNAME:')
                name = P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16, False))
                if not conn.connected:
                    return
                if len(name) < 6:
                    conn.Sendall(chr(P.ORANGE)+'\ruSERNAME MUST BE 6 TO 16 CHARACTERS\rLONG, TRY AGAIN\r')
                    time.sleep(2)
                    if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                        conn.Sendall(TT.Fill_Line(14,32)+TT.Fill_Line(15,32)+(chr(P.CRSR_UP))*3)
                    else:
                        conn.Sendall(TT.set_CRSR(0,14)+(' '*80)+(chr(P.CRSR_UP)*3))
                elif name == '_guest_':
                    conn.Sendall(chr(P.ORANGE)+'\riNVALID NAME\rTRY AGAIN\r')
                    time.sleep(2)
                    if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                        conn.Sendall(TT.Fill_Line(14,32)+TT.Fill_Line(15,32)+(chr(P.CRSR_UP))*3)
                    else:
                        conn.Sendall(TT.set_CRSR(0,14)+(' '*80)+(chr(P.CRSR_UP)*3))
                elif name != conn.username:
                    tentry = conn.bbs.database.chkUser(name)
                    if tentry != None:
                        conn.Sendall(chr(P.ORANGE)+'\ruSERNAME ALREADY TAKEN\rTRY AGAIN:\r')
                        time.sleep(2)
                        if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                            conn.Sendall(TT.Fill_Line(14,32)+TT.Fill_Line(15,32)+(chr(P.CRSR_UP))*3)
                        else:
                            conn.Sendall(TT.set_CRSR(0,14)+(' '*80)+(chr(P.CRSR_UP)*3))
                    else:
                        conn.bbs.database.updateUser(uentry.doc_id,name,None,None,None,None,None,None)
                        conn.username = name
                        n = True
                else:   #Same old username
                    n = True
        elif k == b'B': #First name
            conn.Sendall('\r'+chr(P.CRSR_UP))
            if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                conn.Sendall(TT.Fill_Line(13,32))
            else:
                conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP))
            conn.Sendall('fIRST NAME:')
            fname = P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16))
            if not conn.connected:
                return
            conn.bbs.database.updateUser(uentry.doc_id,None,None,fname,None,None,None,None)
        elif k == b'C': #Last name
            conn.Sendall('\r'+chr(P.CRSR_UP))
            if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                conn.Sendall(TT.Fill_Line(13,32))
            else:
                conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP))
            conn.Sendall('lAST NAME:')
            lname = P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16))
            if not conn.connected:
                return
            conn.bbs.database.updateUser(uentry.doc_id,None,None,None,lname,None,None,None)
        elif k == b'D': #Birthdate
            conn.Sendall('\r'+chr(P.CRSR_UP))
            if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                conn.Sendall(TT.Fill_Line(13,32))
            else:
                conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP))
            bday = conn.ReceiveDate('\rbIRTHDATE: ',datetime.date(1900,1,1),datetime.date.today(),datetime.date(1970,1,1))
            if not conn.connected:
                return
            conn.bbs.database.updateUser(uentry.doc_id,None,None,None,None,bday.strftime("%d/%m/%Y"),None,None)
        elif k == b'E': #Country
            conn.Sendall('\r'+chr(P.CRSR_UP))
            if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                conn.Sendall(TT.Fill_Line(13,32))
            else:
                conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP)) 
            conn.Sendall('cOUNTRY:')
            country = P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16))
            if not conn.connected:
                return
            conn.bbs.database.updateUser(uentry.doc_id,None,None,None,None,None,country,None)
        elif k == b'F': #Password
            n = 0
            conn.Sendall('\r'+chr(P.CRSR_UP))
            while n < 3:
                if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                    conn.Sendall(TT.Fill_Line(13,32))
                else:
                    conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP))
                conn.Sendall('oLD PASSWORD:')
                pw = P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16, True))
                if not conn.connected:
                    return
                if conn.bbs.database.chkPW(uentry,pw,False):
                    m = False
                    conn.Sendall('\r'+chr(P.CRSR_UP))
                    while not m:
                        if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                            conn.Sendall(TT.Fill_Line(13,32))
                        else:
                            conn.Sendall(TT.set_CRSR(0,13)+(' '*40)+chr(P.CRSR_UP))                        
                        conn.Sendall('nEW PASSWORD:')
                        pw = P.toASCII(conn.ReceiveStr(bytes(keys,'ascii'), 16, True))
                        if not conn.connected:
                            return
                        if len(pw) < 6:
                            conn.Sendall(chr(P.ORANGE)+'\rpASSWORD MUST BE 6 TO 16 CHARACTERS\rLONG, TRY AGAIN\r')
                            time.sleep(2)
                            if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                                conn.Sendall(TT.Fill_Line(14,32)+TT.Fill_Line(15,32)+(chr(P.CRSR_UP))*3)
                            else:
                                conn.Sendall(TT.set_CRSR(0,14)+(' '*80)+(chr(P.CRSR_UP)*3))
                        else:
                            conn.bbs.database.updateUser(uentry.doc_id,None,pw,None,None,None,None,None)
                            m = True
                            n = 3
                else:
                    conn.Sendall('\riNCORRECT PASSWORD\rTRY AGAIN\r')
                    time.sleep(2)
                    if conn.QueryFeature(TT.LINE_FILL) < 0x80:
                        conn.Sendall(TT.Fill_Line(14,32)+TT.Fill_Line(15,32)+(chr(P.CRSR_UP))*3)
                    else:
                        conn.Sendall(TT.set_CRSR(0,14)+(' '*80)+(chr(P.CRSR_UP)*3))
                    n += 1

# Display user list
def UserList(conn:Connection):
    if conn.menu != -1:
        conn.MenuStack.append([conn.MenuDefs,conn.menu])
        conn.menu = -1
    # Init Menu parameter dictionary if needed
    if conn.MenuParameters == {}:
        conn.MenuParameters['current'] = 0

    # Start with barebones MenuDic
    MenuDic = { 
                b'_': (MenuBack,(conn,),"Previous Menu",0,False),
                b'\r': (UserList,(conn,),"",0,False)
              }	
 
     # Select screen output
    conn.Sendall(TT.to_Screen())
    # Sync
    conn.Sendall(chr(0)*2)
    # # Text mode
    conn.Sendall(TT.to_Text(0,0,0))
    RenderMenuTitle(conn,"User list")

    users = conn.bbs.database.getUsers()
    digits = len(str(max(users[:])[0]))
    tml = '<WHITE> ID         Username<BR><BR><LTGREEN>'
    #conn.Sendall(chr(P.WHITE)+" id         uSERNAME\r\r"+chr(P.LT_GREEN))
    if conn.QueryFeature(TT.LINE_FILL) < 0x80:
        #conn.Sendall(TT.Fill_Line(4,64))
        tml += '<LFILL row=4 code=64>'
    else:
        #conn.Sendall(chr(P.CRSR_UP)+(chr(P.HLINE)*40))
        tml += '<CRSRU><HLINE n=40>'
    conn.SendTML(tml)

    pages = int((len(users)-1) / 18) + 1
    count = len(users)
    start = conn.MenuParameters['current'] * 18
    end = start + 17
    if end >= count:
        end = count - 1

    #Add pagination keybindings to MenuDic
    if pages > 1:
        if conn.MenuParameters['current'] == 0:
            page = pages-1
        else:
            page = conn.MenuParameters['current']-1
        MenuDic[b'<'] = (SetPage,(conn,page),'Previous Page',0,False)
        if conn.MenuParameters['current'] == pages-1:
            page = 0
        else:
            page = conn.MenuParameters['current']+1
        MenuDic[b'>'] = (SetPage,(conn,page),'Next Page',0,False)

    x = 0
    for x in range(start, end + 1):
        if x % 4 == 0 or x % 4 == 1:
            color1 = P.LT_BLUE
            color2 = P.GREY3
        if x % 4 == 2 or x % 4 == 3:
            color1 = P.CYAN
            color2 = P.YELLOW
        KeyLabel(conn, str(users[x][0]).zfill(digits), '   '+users[x][1]+'\r', x % 2)
    else:
        lineasimpresas = end - start + 1
        if lineasimpresas < 18:
            for x in range(18 - lineasimpresas):
                conn.Sendall('\r')
    conn.SendTML(f' <GREY3><RVSON><LARROW> <LTGREEN>Prev. Menu <GREY3>&lt; <LTGREEN>Prev.Page <GREY3>&gt; <LTGREEN>Next Page  <RVSOFF><BR>'
                f'<WHITE> [{conn.MenuParameters["current"]+1}/{pages}]<CYAN> Selection:<WHITE> ')
    conn.Sendall(chr(255) + chr(161) + 'seleksioneunaopsion,')
    time.sleep(1)
    # Select screen output
    conn.Sendall(TT.to_Screen())
    return MenuDic

def GetTerminalFeatures(conn:Connection, display = True):

    conn.SendTML(f'<CLR><LTBLUE>Terminal ID: <WHITE>{conn.TermString.decode("utf-8")}<BR>'
                f'<LTBLUE>Turbo56K version: <WHITE>{conn.T56KVer}<BR><PAUSE n=0.5>')

    if b"RETROTERM-SL" in conn.TermString:
        _LOG('SwiftLink mode, audio streaming at 7680Hz',id=conn.id,v=3)
        conn.samplerate = 7680
    if conn.T56KVer > 0.5:
        conn.SendTML('<LTBLUE>Checking some terminal features<BR>')
        result = [None]*(TT.TURBO56K_LCMD-127)
        for cmd in [129,130,179]:
            conn.SendTML(f'<GREY3>{TT.T56K_CMD[cmd]}: {"<LTGREEN><CHECKMARK>" if conn.QueryFeature(cmd)< 0x80 else "<RED>x"}<BR>')
    conn.Sendall('\r')
    if conn.QueryFeature(131) < 0x80:
        conn.SendTML(f'<GREY3>PCM audio samplerate <YELLOW>{conn.samplerate}Hz<BR>')
    time.sleep(0.5)

#######################################################
##					  BBS Loop						 ##
#######################################################

def BBSLoop(conn:Connection):

    try:
        # Sync
        conn.Sendall(chr(0)*2)
        # Send speech message
        conn.Sendall(TT.to_Speech() + '.bienvenido,p\'r2esioneritarn,')
        time.sleep(1)
        if conn.bbs.lang == 'es':
            pt = "presione RETURN..."
        else:
            pt = "press RETURN..."

        welcome = f'''<RESET><SETOUTPUT o=True><TEXT>
<CLR><LOWER><CYAN><BR>
{conn.bbs.WMess}<BR>
RetroBBS v{conn.bbs.version:.2f}<BR>
running under:<BR>
{conn.bbs.OSText}<BR>
<LTBLUE>{pt}<BR>'''

        conn.SendTML(welcome)

        # Connected, wait for the user to press RETURN
        WaitRETURN(conn)

        # Ask for ID and supported TURBO56K version
        conn.Sendall(chr(TT.CMDON) + chr(TT.VERSION) + chr(TT.CMDOFF))
        time.sleep(1)
        datos = ""
        conn.socket.settimeout(10.0)
        datos = conn.Receive(2)
        conn.socket.settimeout(_tout)
        _LOG('ID:', datos,id=conn.id,v=4)
        if datos == b"RT":
            datos = conn.Receive(20)
            _LOG('Terminal: ['+ bcolors.OKGREEN + str(datos) + bcolors.ENDC + ']',id=conn.id,v=4)
            dato1 = conn.Receive(1)
            dato2 = conn.Receive(1)
            _LOG('TURBO56K version: '+ bcolors.OKGREEN + str(ord(dato1)) + '.' + str(ord(dato2)) + bcolors.ENDC,id=conn.id,v=4) 

            t56kver = ord(dato1)+((ord(dato2))/10)

            if t56kver > 0.4:
                conn.TermString = datos
                conn.T56KVer = t56kver
                GetTerminalFeatures(conn)
                if conn.QueryFeature(129) < 0x80 and conn.QueryFeature(130) < 0x80 and conn.QueryFeature(179) < 0x80:
                    _LOG('Sending intro pic',id=conn.id,v=4)
                    bg = FT.SendBitmap(conn,conn.bbs.Paths['bbsfiles']+'splash.art',lines=12,display=False)
                    _LOG('Spliting Screen',id=conn.id,v=4)
                    conn.Sendall(TT.split_Screen(12,False,ord(bg),0))
                time.sleep(1)
                Done = False
                while not Done:
                    r = conn.SendTML('<CLR><INK c=1>(L)ogin OR (G)uest?<PAUSE n=1><INKEYS k="LGS">')
                    if not conn.connected:
                        return()
                    t = r['_A']
                    if t == b'L':
                        SignIn(conn)
                        if conn.username != '_guest_':
                            conn.Sendall(chr(0)*2+TT.split_Screen(0,False,0,0))
                            SlideShow(conn,'',conn.bbs.Paths['bbsfiles']+'intro/')
                            conn.Sendall(TT.enable_CRSR())
                            Done = True
                    elif t == b'G':
                        conn.Sendall(chr(0)*2+TT.split_Screen(0,False,0,0)+chr(P.CLEAR))
                        SlideShow(conn,'',conn.bbs.Paths['bbsfiles']+'intro/')
                        conn.Sendall(TT.enable_CRSR())
                        Done = True
                    else:
                        conn.Sendall(chr(0)*2+TT.split_Screen(0,False,0,0))
                        Done = True
            else:
                _LOG('Old terminal detected - Terminating',id=conn.id)
                conn.SendTML('Please user RETROTERM v0.13 or posterior<BR> For the latest version visit<BR>WWW.PASTBYTES.COM/RETROTERM<BR><WHITE>')
                conn.connected = False

            #Increment visit counters
            conn.bbs.visits += 1            #Session counter
            conn.bbs.database.newVisit(conn.username)    #Total counter


            # Display the main menu

            conn.menu = 0		# Starting at the main menu
            conn.MenuDefs = GetKeybindings(conn,0)
            SendMenu(conn)

            while conn.connected == True and _run == True:
                data = conn.Receive(1)
                _LOG('received "'+bcolors.OKBLUE+str(data)+bcolors.ENDC+'"',id=conn.id,v=4)
                if data != b'' and conn.connected == True:
                    if data in conn.MenuDefs:
                        if conn.userclass >= conn.MenuDefs[data][3]:
                            prompt = crop(conn.MenuDefs[data][2], 20)   #conn.MenuDefs[data][2] if len(conn.MenuDefs[data][2])<20 else conn.MenuDefs[data][2][:17]+'...'
                            conn.Sendall(P.toPETSCII(prompt))	#Prompt
                            time.sleep(1)
                            wait = conn.MenuDefs[data][4]
                            Function = conn.MenuDefs[data][0]
                            res = Function(*conn.MenuDefs[data][1])
                            if isinstance(res,dict):
                                conn.MenuDefs = res
                            elif data!=b'\r':
                                if wait:
                                    WaitRETURN(conn,60.0*5)
                                    conn.Sendall(TT.enable_CRSR())	#Enable cursor blink just in case
                                Function = conn.MenuDefs[b'\r'][0]
                                res = Function(*conn.MenuDefs[b'\r'][1])
                                if isinstance(res,dict):
                                    conn.MenuDefs = res
                        else:
                            conn.Sendall('yOU CANT ACCESS THIS AREA')
                            time.sleep(2)
                            SendMenu(conn)
                    else:
                        continue
                else:
                    _LOG('no more data from', conn.addr, id=conn.id)
                    break

        else:
            conn.SendTML("""<CYAN><BR>This BBS requires a terminal<BR>compatible with TURBO56K 0.3 or newer.<BR>
For the lastest version visit<BR>WWW.PASTBYTES.COM/RETROTERM<BR><LTBLUE>Disconnected...""")
            time.sleep(1)
            _LOG('Not a compatible terminal, disconnecting...',id=conn.id,v=2)
            # Clean up the connection
            conn.socket.close()
    finally:
        # Clean up the connection
        conn.socket.close()
        _LOG('Disconnected',id=conn.id,v=3)


## Connection check thread ##
def ConnTask():
    global conlist
    global bbs_instance
    global _semaphore

    while _run:
        time.sleep(1) # check once per second

        # Reload configuration file if it has been modified and there's nobody online
        if len(conlist) == 0:
            if getmtime(config_file) != bbs_instance.cfgmts:
                _LOG('Config file modified',v=2)
                _semaphore = True
                ConfigRead()
                bbs_instance.start()    #Restart
                _semaphore = False

        for t in range(1,bbs_instance.lines+1):
            if t in conlist:				#Find closed connections
                if not conlist[t][0].is_alive():
                    conlist[t][1].Close()
                    if conlist[t][1].userclass != 0:
                        bbs_instance.database.logoff(conlist[t][1].userid,conlist[t][1].outbytes,conlist[t][1].inbytes)
                    del conlist[t][1]
                    try:
                        conlist[t][0].join()
                    except:
                        pass
                    conlist.pop(t)
                    _LOG('Slot freed - Awaiting a connection',v=3)

#######################################################
##              		MAIN                         ##
#######################################################

# Initialize variables

parser = argparse.ArgumentParser(description='Python BBS server for Turbo56K enabled terminals')
parser.add_argument('-v', dest='verb', type=int, choices=range(1,5),nargs='?', const=1, default=1, help='Verbosity level (1-4): 1 = Errors only | 4 = All logs')
parser.add_argument('-c', dest='config', type=str, nargs='?', const='config.ini', default='config.ini', help='Path to the configuration file to be used')

if AA.wavs != True:
    _LOG('Audio fileformats not available!', v=2)

if AA.meta != True:
    _LOG('Audio Metadata not available!', v=2)

args = parser.parse_args()

set_verbosity(args.verb)

#Set configuration file
config_file = args.config

_semaphore = False  #

bbs_instance = BBS('','',0)
bbs_instance.version = _version
#Check OS type
bbs_instance.OSText = platform.system()
if 'Linux' in bbs_instance.OSText:
    #Get distro
    mi = subprocess.check_output(["hostnamectl", "status"], universal_newlines=True)
    m = re.search('Operating System: (.+?)\n', mi)
    bbs_instance.OSText = m.group(1)
else:
    #Add OS version
    bbs_instance.OSText = bbs_instance.OSText + platform.release()

print('\n\nRetroBBS v%.2f (c)2021-2023\nby Pablo Roldán(durandal) and\nJorge Castillo(Pastbytes)\n\n'%_version)

# Parse plugins
# p_mods = [importlib.import_module(name) for finder, name, ispkg in iter_namespace(plugins)]
# for a in p_mods:
#     if 'setup' in dir(a):
#         fname,parms = a.setup()
#         PlugDict[fname] = (a.plugFunction,parms) 
#         _LOG('Loaded plugin: '+fname,v=4)

# Init plugins
bbs_instance.plugins = EX.RegisterPlugins()
# Init encoders
bbs_instance.encoders = EX.RegisterEncoders()
# Register TML tags
EX.RegisterTPLtags()

# Read config file
ConfigRead()

bbs_instance.start()

# Register CTRL-C handler
signal.signal(signal.SIGINT, signal_handler)

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Bind the socket to the port
server_address = (bbs_instance.ip, bbs_instance.port)
_LOG('Initializing server on %s port %s' % server_address,v=3)
sock.bind(server_address)

# Listen for incoming connections. Max 2 connections in queue
sock.listen(2)

#List of current active connections
conlist = {}

conthread = threading.Thread(target = ConnTask, args = ())
conthread.start()

while True:
    # Wait for a connection
    _LOG('Awaiting a connection',v=3)
    c, c_addr = sock.accept()

    while _semaphore:   # Wait for _semaphore to be False (config finished updating)
        pass

    newid = 1
    for r in range(1,bbs_instance.lines+1):			#Find free id
        if r not in conlist:
            newid = r
            newconn = Connection(c,c_addr,bbs_instance,newid)
            conlist[newid] = [threading.Thread(target = BBSLoop, args=(newconn,)),newconn]
            conlist[newid][0].start()
            break
    else:   # No free slot, refuse connection
        c.sendall(bytes(P.toPETSCII(bbs_instance.BSYMess),'latin1'))
        c.close()
    
