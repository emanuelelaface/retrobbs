###############################################################################
# Podcast Plugin 20240826 written by Emanuele Laface                          #
#                                                                             #
# This plugin requires podsearch ad feedpareser to work and it is a Python    #
# implementaiton of https://performance-partners.apple.com/search-api         #
# #############################################################################

from common import turbo56k as TT
from common.helpers import crop
from common.connection import Connection

import string
import podsearch
import feedparser

###############
# Plugin setup
###############
def setup():
    fname = "PODCAST"
    parpairs = []
    return(fname,parpairs)

###################################
# Plugin callable function
###################################
def plugFunction(conn:Connection):

    columns,lines = conn.encoder.txt_geo

    def PodcastTitle(conn:Connection):
        conn.SendTML(f'<WINDOW top=0 bottom={lines-1}><CLR><YELLOW>Search internet podcasts<BR>')
        if conn.QueryFeature(TT.LINE_FILL) < 0x80:
            if 'MSX' in conn.mode:
                conn.SendTML('<GREEN><LFILL row=1 code=23>')
            else:
                conn.SendTML('<GREEN><LFILL row=1 code=64>')
        else:
            conn.SendTML('<GREEN><HLINE n=40>')
        conn.Sendall(TT.set_Window(2,lines-1))	#Set Text Window
    ecolors = conn.encoder.colors
    conn.Sendall(TT.to_Text(0,ecolors['BLACK'],ecolors['BLACK']))
    loop = True
    while loop == True:
        PodcastTitle(conn)
        conn.SendTML('<BR>Search: <BR>(<BACK> to exit)<CRSRU><CRSRL n=3>')
        keys = string.ascii_letters + string.digits + ' +-_,.$%&'
        termino = ''
        #Receive search term
        while termino == '':
            termino = conn.ReceiveStr(bytes(keys,'ascii'), columns-10, False)
            if conn.connected == False :
                return()
            if termino == '_':
                conn.Sendall(TT.set_Window(0,lines))
                return()
        conn.SendTML('<BR><BR>Searching...<SPINNER><CRSRL>')
        searchRes = searchPodcast(termino)
        if searchRes == False:
            conn.SendTML('<ORANGE>Service unavailable...<PAUSE n=2>')
            continue
        elif len(searchRes) == 0:
            conn.SendTML('<YELLOW>No results...<PAUSE n=2>')
            continue
        page = 0
        npodcasts = len(searchRes)
        pcount = lines-10
        if 'MSX' in conn.mode:
            grey = '<GREY>'
        else:
            grey = '<GREY1>'
        while True:
            conn.SendTML('<CLR><BR>Results:<BR><BR>')
            for i in range(pcount*page, min(pcount*(page+1),npodcasts)):
                if i > 9:
                    pos = str(i)
                else:
                    pos = " "+str(i)
                podcastName = crop(searchRes[i].name,columns-10,conn.encoder.ellipsis).ljust(columns-10)
                conn.SendTML(f' <BLUE>{pos} {grey}{podcastName}<BR>')
            if npodcasts < pcount:
                conn.SendTML(f'<BR><RED><BACK>{grey}Exit<BR>')
                conn.SendTML(f'<RED><KPROMPT t=RETURN>{grey}Search Again<BR>')
            else:
                conn.SendTML(f'<BR><RED>P{grey}rev Page,')
                conn.SendTML(f'<RED>N{grey}ext Page,')
                conn.SendTML(f'<RED><BACK>{grey}Exit<BR>')
                conn.SendTML(f'<KPROMPT t=RETURN>{grey}Search Again<BR>')
            conn.SendTML('<BR>Select:')
            sel = conn.ReceiveStr(bytes(keys,'ascii'), 10, False)
            if sel.upper() == 'P':
                page = max(0,page-1)
            if sel.upper() == 'N':
                page = min(npodcasts//pcount, page+1)
            if sel == '':
                conn.Sendall(TT.set_Window(0,lines))
                break
            if sel == '_':
                conn.Sendall(TT.set_Window(0,lines))
                return()
            if sel.isdigit() and int(sel) < npodcasts:
                episodes = getEpisodes(searchRes[int(sel)])
                if episodes == False:
                    conn.SendTML('<ORANGE>Service unavailable...<PAUSE n=2>')
                    continue
                elif len(episodes) == 0:
                    conn.SendTML('<YELLOW>No episodes...<PAUSE n=2>')
                    continue
                eppage = 0
                nepisodes = len(episodes)
                eppcount = lines-10
                if 'MSX' in conn.mode:
                    grey = '<GREY>'
                else:
                    grey = '<GREY1>'
                while True:
                    conn.SendTML(f'<CLR><BR>{str(nepisodes)} Episodes:<BR><BR>')
                    for i in range(eppcount*eppage, min(eppcount*(eppage+1),nepisodes)):
                        if i > 9:
                            eppos = str(i)
                        else:
                            eppos = " "+str(i)
                        episodeName = crop(episodes[i]['title'],columns-10,conn.encoder.ellipsis).ljust(columns-10)
                        conn.SendTML(f' <BLUE>{eppos} {grey}{episodeName}<BR>')
                    if nepisodes < eppcount:
                        conn.SendTML(f'<BR><RED><BACK>{grey}Exit<BR>')
                        conn.SendTML(f'<RED><KPROMPT t=RETURN>{grey}Back to Podcasts<BR>')
                    else:
                        conn.SendTML(f'<BR><RED>P{grey}rev Page,')
                        conn.SendTML(f'<RED>N{grey}ext Page,')
                        conn.SendTML(f'<RED><BACK>{grey}Exit<BR>')
                        conn.SendTML(f'<KPROMPT t=RETURN>{grey}Back to Podcasts<BR>')
                    conn.SendTML('<BR>Select:')
                    epsel = conn.ReceiveStr(bytes(keys,'ascii'), 10, False)
                    if epsel.upper() == 'P':
                        eppage = max(0,eppage-1)
                    if epsel.upper() == 'N':
                        eppage = min(nepisodes//eppcount, eppage+1)
                    if epsel == '':
                        conn.Sendall(TT.set_Window(0,lines))
                        break
                    if epsel == '_':
                        conn.Sendall(TT.set_Window(0,lines))
                        return()
                    if epsel.isdigit() and int(epsel) < nepisodes:
                        url = episodes[int(epsel)]['links'][0]['href']
                        fullname = episodes[int(epsel)]['title']
                        conn.SendTML(f'<WEBAUDIO url={url}, direct="{fullname}">')
                        conn.SendTML(f'<NUL><CURSOR><TEXT border={ecolors["BLACK"]} background={ecolors["BLACK"]}>')
                PodcastTitle(conn)

    conn.Sendall(TT.set_Window(0,lines))	#Set Text Window

def searchPodcast(termino):
    try:
        query = podsearch.search(termino)
    except:
        return False
    return query
def getEpisodes(podcast):
    try:
        query = feedparser.parse(podcast.feed)['entries']
    except:
        return False
    return query
