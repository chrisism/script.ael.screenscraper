#!/usr/bin/python -B
# -*- coding: utf-8 -*-

#
# List media types (asset/artwork types or kinds) for ScreenScraper.
#

# --- Python standard library ---
from __future__ import unicode_literals
from __future__ import unicode_literals
import os, sys
from collections import OrderedDict

import pprint, json
import logging

logging.basicConfig(format = '%(asctime)s %(module)s %(levelname)s: %(message)s',
                datefmt = '%m/%d/%Y %I:%M:%S %p', level = logging.DEBUG)
logger = logging.getLogger(__name__)

from resources.lib.scraper import ScreenScraper
from ael.utils import kodi, text
from ael import constants

# --- Test data -----------------------------------------------------------------------------------
games = {
    # Console games
    'metroid'                : ('Metroid', 'Metroid.zip', 'Nintendo SNES'),
    'mworld'                 : ('Super Mario World', 'Super Mario World.zip', 'Nintendo SNES'),
    'sonic_megaDrive'        : ('Sonic the Hedgehog', 'Sonic the Hedgehog (USA, Europe).zip', 'Sega Mega Drive'),
    'sonic_genesis'          : ('Sonic the Hedgehog', 'Sonic the Hedgehog (USA, Europe).zip', 'Sega Genesis'),
    'chakan'                 : ('Chakan', 'Chakan (USA, Europe).zip', 'Sega MegaDrive'),
    'ff7'                    : ('Final Fantasy VII', 'Final Fantasy VII (USA) (Disc 1).iso', 'Sony PlayStation'),
    'console_wrong_title'    : ('Console invalid game', 'mjhyewqr.zip', 'Sega MegaDrive'),
    'console_wrong_platform' : ('Sonic the Hedgehog', 'Sonic the Hedgehog (USA, Europe).zip', 'mjhyewqr'),

    # MAME games
    'atetris'             : ('Tetris (set 1)', 'atetris.zip', 'MAME'),
    'mslug'               : ('Metal Slug - Super Vehicle-001', 'mslug.zip', 'MAME'),
    'dino'                : ('Cadillacs and Dinosaurs (World 930201)', 'dino.zip', 'MAME'),
    'MAME_wrong_title'    : ('MAME invalid game', 'mjhyewqr.zip', 'MAME'),
    'MAME_wrong_platform' : ('Tetris (set 1)', 'atetris.zip', 'mjhyewqr'),
}
# --- Settings -----------------------------------------------------------------------------------
use_cached_ScreenScraper_get_gameInfo = True

# --- main ---------------------------------------------------------------------------------------
if use_cached_ScreenScraper_get_gameInfo:
    filename = 'assets/ScreenScraper_get_gameInfo.json'
    print('Loading file "{}"'.format(filename))
    f = open(filename, 'r')
    json_str = f.read()
    f.close()
    json_data = json.loads(json_str)
else:
    # --- Create scraper object ---
    scraper_obj = ScreenScraper()
    scraper_obj.set_verbose_mode(False)
    scraper_obj.set_debug_file_dump(True, os.path.join(os.path.dirname(__file__), 'assets'))
    status_dic = kodi.new_status_dic('Scraper test was OK')
    # --- Get candidates ---
    # candidate_list = scraper_obj.get_candidates(*common.games['metroid'])
    # candidate_list = scraper_obj.get_candidates(*common.games['mworld'])
    candidate_list = scraper_obj.get_candidates(*games['sonic'], status_dic = status_dic)
    # candidate_list = scraper_obj.get_candidates(*common.games['chakan'])
    # --- Get jeu_dic and dump asset data ---
    json_data = scraper_obj.get_gameInfos_dic(candidate_list[0], status_dic = status_dic)
# pprint.pprint(json_data)
jeu_dic = json_data['response']['jeu']

# List first level dictionary values
print('\nListing jeu_dic first level dictionary keys')
for key in sorted(jeu_dic): print(key)

# --- Dump asset data ---
medias_list = jeu_dic['medias']
table = [
    ['left', 'left', 'left'],
    ['Type', 'Region', 'Format'],
]
for media_dic in medias_list:
    region = media_dic['region'] if 'region' in media_dic else None
    table.append([
        str(media_dic['type']), str(region), str(media_dic['format'])
    ])
print('\nThere are {} assets'.format(len(medias_list)))
print('\n'.join(text.render_table_str(table)))
