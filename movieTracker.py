#!/usr/bin/env python
import sys
import requests
from config import debug,API_KEY,JACKETT_PORT,JACKETT_IP,BOT_TOKEN,ALLOWED_USERNAMES
import feedparser
import urllib
import requests
import io
from tinydb import TinyDB, Query, where
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def writeToJson(data,fileName):
    import json
    import os

    f = open(os.path.join('outputs', fileName+'.json'),"w")
    f.write( json.dumps(data) )
    f.close()  


def sizeof_fmt(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def getFeed(searchQuery):
    
    feedUrl = ('http://'+JACKETT_IP+':'+JACKETT_PORT+'/api/v2.0/indexers/all/results/torznab/api?apikey='+API_KEY+'&t=search&cat=&q='+urllib.parse.quote(searchQuery))
    feedBytes = requests.get(feedUrl, timeout=1000)
    feedXML = io.BytesIO(feedBytes.content)
    feed = feedparser.parse(feedXML)
    return feed


def filterFeed(feed, searchQuery, blackWordList):
    # Filter feed
    queryWords = searchQuery.split(' ')

    goodentries = []
    for entryIdx in range(0,len(feed['entries'])) :
        # Check if entry contains all search query words
        badEntry = False
        for queryWord in queryWords:
            if not queryWord.lower() in feed['entries'][entryIdx]['title'].lower():
                badEntry = True
                break
        
        if not badEntry:
            # Check if entry contains blacklisted words
            badEntry = False
            for blackWord in blackWordList:
                if blackWord.lower() in feed['entries'][entryIdx]['title'].lower():
                    badEntry = True
                    break
        
        if not badEntry:
            goodentries.append(feed['entries'][entryIdx])
    
    feed['entries'] = goodentries

    return feed

def filterIgnored(feed,movie):
    # Get ignored list
    ignoreds = movieDB_get_ignored(movie)
    # Delete ignoreds from feed
    for ignored in ignoreds:
        for entryIdx, entry in enumerate(feed['entries']):
            if entry['title'] == ignored:
                feed['entries'].pop(entryIdx)
                break
    return feed



def movieDB_exists(movieQuery,ignored):
    Search = Query()
    if movieDB.search((Search.movieQuery == movieQuery) & (Search.ignored == ignored))   == []:
        return False
    else:
        return True

def movieDB_insert(movieQuery, ignored):
    if not movieDB_exists(movieQuery, ignored):
        movieQueryDict = {'movieQuery':movieQuery,'ignored':ignored}
        movieDB.insert(movieQueryDict)

def movieDB_get_movies():
    Search = Query()
    titles_dict = movieDB.search((Search.ignored == None))
    titles = []
    for title_obj in titles_dict:
        titles.append(title_obj["movieQuery"])
    return titles

def movieDB_get_ignored(movieQuery):
    Search = Query()
    ignored_dict = movieDB.search((Search.ignored != None) & (Search.movieQuery == movieQuery))
    ignoreds = []
    for title_obj in ignored_dict:
        ignoreds.append(title_obj["ignored"])
    return ignoreds

def movieDB_delete_movie(movie):
    movieDB.remove(where('movieQuery') == movie)
    return



def get_feed(searchQuery):
    blackWordList = ['latino']

    feed = getFeed(searchQuery)
    feed = filterFeed(feed, searchQuery, blackWordList)
    feed = filterIgnored(feed, searchQuery)
    return feed

def bot_send(text):
    #context.bot.send_message(chat_id=update.effective_chat.id,text=text, parse_mode=telegram.ParseMode.HTML)
    return




from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler

import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)



# Funciones
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Hi")

def unknown(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

def caps(update, context):
    text_caps = ' '.join(context.args).upper()
    context.bot.send_message(chat_id=update.effective_chat.id, text=text_caps)

def watchlist(update, context):
    movies = movieDB_get_movies()
    if movies == []:
        textresponse = 'No movies here. Send me what you want to add.'
    else:
        textresponse = ''
        for movie in movies:
            textresponse = textresponse + movie +  '\n'
    
    context.bot.send_message(chat_id=update.effective_chat.id, text=textresponse)


def get_movieupdate(movie,mode):
    def generateText(feed,movie,mode):
        reply_markup = None

        if feed['entries'] == []:
            textResponse=movie+': No updates...'
        else:
            if mode == 'update':
                emoji = '❗'
                keyboard = [[InlineKeyboardButton("Ignore", callback_data='ignore$'+movie)],[InlineKeyboardButton("Delete", callback_data='delete$'+movie)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            elif mode == 'ignore':
                emoji = '➖'

            textResponse = movie+': '+ str(len(feed['entries'])) +' nuevos resultados\n\n'
            limit = 5
            count = 0
            for entry in feed['entries']:
                textResponse = textResponse + emoji + ' ' + entry['title'] + '\n' + '💾 ' +sizeof_fmt(int(entry['size'])) + '\n\n'
                if limit < count:
                    break
                count = count + 1

       
        return textResponse,reply_markup

    feed  = get_feed(movie)

    movieUpdate = {'feed':feed}

    if feed['entries'] == []:
        movieUpdate['newResults']=False
    else:
        movieUpdate['newResults']=True

    movieUpdate['text'],movieUpdate['reply_markup'] = generateText(feed,movie,mode)     
    
    return movieUpdate

def updatelist(update, context):
    movies = movieDB_get_movies()
    movieUpdates = []
    update.message.reply_text('Updating...')
    # Get updates
    for movie in movies:
        movieUpdate = get_movieupdate(movie,'update')
        movieUpdates.append(movieUpdate)
    # Send updates
    for movieUpdate in movieUpdates:
        update.message.reply_text(text=movieUpdate['text'],reply_markup=movieUpdate['reply_markup'])

def button(update, context):
    query = update.callback_query
    query.answer()
    query_array = query.data.split('$')

    query_command = query_array[0]

    if query_command == 'ignore':
        movie = query_array[1]

        movieUpdate = get_movieupdate(movie,'ignore')

        # Add to ignore
        for entry in movieUpdate['feed']['entries']:
            movieDB_insert(movie,entry['title'])
        
        query.edit_message_text(text=movieUpdate['text'],reply_markup=movieUpdate['reply_markup'])
        

    elif query_command == 'delete':
        movie = query_array[1]

        movieDB_delete_movie(movie)
        query.edit_message_text(text=movie+' deleted')
        
    
    elif query_command == 'add':
        movie = query_array[1]

        movieDB_insert(movie,None)

        movieUpdate = get_movieupdate(movie,'update')
        query.edit_message_text(text=movieUpdate['text'],reply_markup=movieUpdate['reply_markup'])
        

    elif query_command == 'cancel':
        query.edit_message_text(text='Cancelado',reply_markup=None)
    
    return




def delete(update, context):
    movies = movieDB_get_movies()
    keyboard = []
    for movie in movies:
        keyboard.append([InlineKeyboardButton(movie, callback_data='delete$'+movie)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Select to delete: ', reply_markup=reply_markup)

def addmovie(update, context):
    movie = update.message.text
    keyboard =  [   [InlineKeyboardButton("Yes", callback_data='add$'+movie)],
                    [InlineKeyboardButton("No", callback_data='cancel')]
                ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Añadir '+movie, reply_markup=reply_markup)
    return 

    

def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)


    # Command Handler
    start_handler = CommandHandler('start', start, Filters.chat(chat_id=ALLOWED_USERNAMES))
    updater.dispatcher.add_handler(start_handler)

    caps_handler = CommandHandler('caps', caps, Filters.chat(chat_id=ALLOWED_USERNAMES))
    updater.dispatcher.add_handler(caps_handler)

    watchlist_handler = CommandHandler('list', watchlist, Filters.chat(chat_id=ALLOWED_USERNAMES))
    updater.dispatcher.add_handler(watchlist_handler)

    updatelist_handler = CommandHandler('update', updatelist, Filters.chat(chat_id=ALLOWED_USERNAMES))
    updater.dispatcher.add_handler(updatelist_handler)

    delete_handler = CommandHandler('delete', delete, Filters.chat(chat_id=ALLOWED_USERNAMES))
    updater.dispatcher.add_handler(delete_handler)

    # Query handlers

    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    
    # Message 
    addmovie_handler = MessageHandler(Filters.text and Filters.chat(chat_id=ALLOWED_USERNAMES), addmovie)
    updater.dispatcher.add_handler(addmovie_handler)

    unknown_handler = MessageHandler(Filters.command and Filters.chat(chat_id=ALLOWED_USERNAMES), unknown)
    updater.dispatcher.add_handler(unknown_handler)

    updater.start_polling()
    updater.idle()


def updatess():
    import datetime
    print("===================================================")
    print(datetime.datetime.now())
    print("===================================================")
    bot = telegram.Bot(token=BOT_TOKEN)
    movies = movieDB_get_movies()
    for movie in movies:
        movieUpdate = get_movieupdate(movie,'update')
        if movieUpdate['newResults']:
            print(movie+' NEW UPDATES!!!')
            for user in ALLOWED_USERNAMES:
                bot.send_message(chat_id=user,text=movieUpdate['text'],reply_markup=movieUpdate['reply_markup'])
        else:
            print(movie+' no new updates')

    return




if __name__ == '__main__':

    movieDB = TinyDB('db.json')
    
    sys.argv = sys.argv[1:]
    if sys.argv == []:
        main()
    elif sys.argv[0] == 'update':
        updatess()
    


