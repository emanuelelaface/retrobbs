##############################################################################
# HVSC Plugin 20240411 written by Emanuele Laface                            #
#                                                                            #
# This plugin uses the HVSC API to search for SID files                      #
# ############################################################################

from common import turbo56k as TT
from common.style import bbsstyle
from common import filetools as FT
from common.helpers import formatX, crop, text_displayer
from common.connection import Connection
from common.bbsdebug import _LOG
from common.imgcvt import cropmodes, PreProcess
from common import audio as AA

import string
import requests
import sys, os
import tempfile
import re

###############
# Plugin setup
###############
def setup():
    fname = "HVSC"
    parpairs = []
    return(fname,parpairs)

###################################
# Plugin callable function
###################################
def plugFunction(conn:Connection):

    def HVSCTitle(conn:Connection):
        conn.SendTML('<WINDOW top=0 bottom=24><CLR><YELLOW>Browse HVSC Database<BR>')
        if conn.QueryFeature(TT.LINE_FILL) < 0x80:
            conn.SendTML('<GREEN><LFILL row=1 code=64>')
        else:
            conn.SendTML('<GREEN><HLINE n=40>')
        conn.Sendall(TT.set_Window(2,24))	#Set Text Window
    ecolors = conn.encoder.colors
    conn.Sendall(TT.to_Text(0,ecolors['BLACK'],ecolors['BLACK']))
    loop = True
    while loop == True:
        HVSCTitle(conn)
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
        searchRes = searchHVSC(termino)
        if len(searchRes) == 0:
            continue
        page = 0
        nsids = len(searchRes)
        while True:
            HVSCTitle(conn)
            conn.SendTML(' <BR><BR>Results:<BR><BR>')
            for i in range(15*page, min(15*(page+1),nsids)):
                if i > 9:
                    pos = str(i)
                else:
                    pos = " "+str(i)
                sidTitle = searchRes[i]['title'][:30].ljust(30)
                sidYear = searchRes[i]['year']
                conn.SendTML(f'<BLACK>[<BLUE>{pos}<BLACK>]<GREY1>{sidTitle} {sidYear}<BR>')
            if nsids < 15:
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
                page = min(nsids//15, page+1)
            if sel == '':
                conn.Sendall(TT.set_Window(0,25))
                break
            if sel == '_':
                conn.Sendall(TT.set_Window(0,25))
                return()
            if sel.isdigit() and int(sel) < nsids:
                url = searchRes[int(sel)]['url']
                sidData = requests.get(url)
                if sidData.ok:
                    sidFile = tempfile.NamedTemporaryFile(suffix='.sid')
                    with open(sidFile.name, "wb") as f:
                        f.write(sidData.content)
                    AA.CHIPStream(conn,sidFile.name,None,True)
                conn.SendTML(f'<NUL><CURSOR><TEXT border={ecolors["BLACK"]} background={ecolors["BLACK"]}>')

    conn.Sendall(TT.set_Window(0,24))	#Set Text Window

def searchHVSC(termino):
    query_url = 'https://www.hvsc.c64.org/api/v1/sids?q='
    dl_url = 'https://www.hvsc.c64.org/download/sids/'
    query = requests.get(query_url+termino)
    if query.ok:
        query_json = query.json()

    res = []
    for i in query_json:
        entry = {}
        if i['title'] == "<?>":
            entry['title'] = "No Title"
        else:
            entry['title'] = i['title']
        entry['url'] = dl_url+str(i['id'])
        year = re.findall(r"[0-9]{4,7}", i['released'])
        if len(year) > 0:
            entry['year'] = year[0]
        else:
            entry['year'] = 'UNKN'
        res.append(entry)
    return res
