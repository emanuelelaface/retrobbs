##############################################################################
# Radio Plugin 20240411 written by Emanuele Laface                           #
#                                                                            #
# This plugin requires pyradios to work and it is a Python implementaiton of #
# https://api.radio-browser.info/ free API (It uses GPL 3).                  #
# ############################################################################

from common import turbo56k as TT
from common.style import bbsstyle
from common import filetools as FT
from common.helpers import formatX, crop, text_displayer
from common.connection import Connection
from common.bbsdebug import _LOG
from common.imgcvt import cropmodes, PreProcess

import string
import requests
import sys, os
from pyradios import RadioBrowser

rb = RadioBrowser()

###############
# Plugin setup
###############
def setup():
    fname = "RADIO"
    parpairs = []
    return(fname,parpairs)

###################################
# Plugin callable function
###################################
def plugFunction(conn:Connection):

    def RadioTitle(conn:Connection):
        conn.SendTML('<WINDOW top=0 bottom=24><CLR><YELLOW>Radio for your C64<BR>')
        if conn.QueryFeature(TT.LINE_FILL) < 0x80:
            conn.SendTML('<GREEN><LFILL row=1 code=64>')
        else:
            conn.SendTML('<GREEN><HLINE n=40>')
        conn.Sendall(TT.set_Window(2,24))	#Set Text Window
    ecolors = conn.encoder.colors
    conn.Sendall(TT.to_Text(0,ecolors['BLACK'],ecolors['BLACK']))
    loop = True
    while loop == True:
        RadioTitle(conn)
        conn.SendTML('<BR>Search: <BR>(<LARROW> to exit)<CRSRU><CRSRL n=3>')
        keys = string.ascii_letters + string.digits + ' +-_,.$%&'
        termino = ''
        #Receive search term
        while termino == '':
            termino = conn.ReceiveStr(bytes(keys,'ascii'), 30, False)
            if conn.connected == False :
                return()
            if termino == '_':
                conn.Sendall(TT.set_Window(0,25))
                return()
        conn.SendTML(' <BR><BR>Results:<BR><BR>')
        searchRes = searchRadio(termino)
        if len(searchRes) == 0:
            continue
        page = 0
        nradios = len(searchRes)
        while True:
            RadioTitle(conn)
            conn.SendTML(' <BR><BR>Results:<BR><BR>')
            for i in range(15*page, min(15*(page+1),nradios)):
                if i > 9:
                    pos = str(i)
                else:
                    pos = " "+str(i)
                radioName = searchRes[i]['name'][:30].ljust(30)
                countryCode = searchRes[i]['countrycode']
                conn.SendTML(f'<BLACK>[<BLUE>{pos}<BLACK>]<GREY1>{radioName} [{countryCode}]<BR>')
            if nradios < 15:
                conn.SendTML(f'<BR><BLACK><RED><LARROW><GREY1>Exit<BR>')
                conn.SendTML(f'<BLACK><RED><KPROMPT t=RETURN><GREY1>Search Again<BR>')
            else:
                conn.SendTML(f'<BR><BLACK><RED>P<GREY1>rev Page,')
                conn.SendTML(f'<BLACK><RED>N<GREY1>ext Page,')
                conn.SendTML(f'<BLACK><RED><LARROW><GREY1>Exit<BR>')
                conn.SendTML(f'<BLACK><KPROMPT t=RETURN><GREY1>Search Again<BR>')
            conn.SendTML('<BR>Select:')
            sel = conn.ReceiveStr(bytes(keys,'ascii'), 30, False)
            if sel == 'P':
                page = max(0,page-1)
            if sel == 'N':
                page = min(nradios//15, page+1)
            if sel == '':
                conn.Sendall(TT.set_Window(0,25))
                break
            if sel == '_':
                conn.Sendall(TT.set_Window(0,25))
                return()
            if sel.isdigit() and int(sel) < nradios:
                url = searchRes[int(sel)]['url']
                conn.SendTML(f'<WEBAUDIO url={url}>')
                conn.SendTML(f'<NUL><CURSOR><TEXT border={ecolors["BLACK"]} background={ecolors["BLACK"]}>')

    conn.Sendall(TT.set_Window(0,24))	#Set Text Window

def searchRadio(termino):
    urls = []
    res = []
    query = rb.search(name=termino, name_exact=False)
    for i in query:
        if i['url'] not in urls:
            res.append(i)
            urls.append(i['url'])
    return res
