# -*- coding: utf-8 -*-
#
# Advanced Emulator Launcher scraping engine for SteamGrid DB.

# Copyright (c) 2020-2021 Chrisism
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.

# --- Python standard library ---
from __future__ import unicode_literals
from __future__ import division

import logging
import json
import re
from datetime import datetime, timedelta

from urllib.parse import quote_plus

# --- AEL packages ---
from ael import constants, platforms, settings
from ael.utils import io, net, kodi, text
from ael.scrapers import Scraper

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------------------------
# SteamGridDB online scraper.
#
# | Site     | https://www.steamgriddb.com        |
# | API info | https://www.steamgriddb.com/api/v2 |
# ------------------------------------------------------------------------------------------------
class SteamGridDB(Scraper):
    # --- Class variables ------------------------------------------------------------------------
    supported_metadata_list = [
    ]
    supported_asset_list = [
        constants.ASSET_BOXFRONT_ID,
        constants.ASSET_CLEARLOGO_ID,
        constants.ASSET_FANART_ID
    ]
    asset_name_mapping = {
        'grids'   : constants.ASSET_BOXFRONT_ID,
        'logos'   : constants.ASSET_CLEARLOGO_ID,
        'heroes'  : constants.ASSET_FANART_ID
    }
    
    # BASE URLS
    API_URL = 'https://www.steamgriddb.com/api/v2/'
    
    # --- Constructor ----------------------------------------------------------------------------
    def __init__(self):
        # --- This scraper settings ---
        self.api_key = settings.getSetting('scraper_steamgriddb_apikey')
        # --- Misc stuff ---
        self.cache_candidates = {}
        self.cache_metadata = {}
        self.cache_assets = {}
        self.all_asset_cache = {}

        cache_dir = settings.getSetting('scraper_cache_dir')
        # --- Pass down common scraper settings ---
        super(SteamGridDB, self).__init__(cache_dir)

    # --- Base class abstract methods ------------------------------------------------------------
    def get_name(self): return 'SteamGridDB'

    def get_filename(self): return 'SteamGridDB'

    def supports_disk_cache(self): return True

    def supports_search_string(self): return True

    def supports_metadata_ID(self, metadata_ID): return False

    def supports_metadata(self): return False

    def supports_asset_ID(self, asset_ID):
        return True if asset_ID in SteamGridDB.supported_asset_list else False

    def supports_assets(self): return True

    # If the SteamGridDB API key is not configured in the settings then disable the scraper
    # and print an error.
    def check_before_scraping(self, status_dic):
        if self.api_key:
            logger.error('SteamGridDB.check_before_scraping() SteamGridDB API key looks OK.')
            return
        logger.error('SteamGridDB.check_before_scraping() SteamGridDB API key not configured.')
        logger.error('SteamGridDB.check_before_scraping() Disabling SteamGridDB scraper.')
        self.scraper_disabled = True
        status_dic['status'] = False
        status_dic['dialog'] = kodi.KODI_MESSAGE_DIALOG
        status_dic['msg'] = (
            'AEL requires your SteamGridDB API key. '
            'Visit https://www.steamgriddb.com/api/v2#section/Authentication for directions about how to get your key '
            'and introduce the API key in AEL addon settings.'
        )

    def get_candidates(self, search_term:str, rom_FN:io.FileName, rom_checksums_FN, platform, status_dic):
        # --- If scraper is disabled return immediately and silently ---    
        if self.scraper_disabled:
            # If the scraper is disabled return None and do not mark error in status_dic.
            logger.debug('SteamGridDB.get_candidates() Scraper disabled. Returning empty data.')
            return None

        # Prepare data for scraping.
        rombase_noext = rom_FN.getBaseNoExt()

        # --- Request is not cached. Get candidates and introduce in the cache ---
        logger.debug('SteamGridDB.get_candidates() search_term          "{0}"'.format(search_term))
        logger.debug('SteamGridDB.get_candidates() rombase_noext        "{0}"'.format(rombase_noext))
        logger.debug('SteamGridDB.get_candidates() AEL platform         "{0}"'.format(platform))
        candidate_list = self._search_candidates(search_term, platform, status_dic)
        if not status_dic['status']: return None

        return candidate_list

    # SteamGridDB does not support metadata
    def get_metadata(self, status_dic):
        return None
    
    # This function may be called many times in the ROM Scanner. All calls to this function
    # must be cached. See comments for this function in the Scraper abstract class.
    def get_assets(self, asset_info_id:str, status_dic):
        # --- If scraper is disabled return immediately and silently ---
        if self.scraper_disabled:
            logger.debug('SteamGridDB.get_assets() Scraper disabled. Returning empty data.')
            return []

        logger.debug('SteamGridDB.get_assets() Getting assets {} for candidate ID "{}"'.format(
            asset_info_id, self.candidate['id']))

        # Get all assets for candidate. _retrieve_all_assets() caches all assets for a candidate.
        # Then select asset of a particular type.
        all_asset_list = self._retrieve_all_assets(self.candidate, status_dic)
        if not status_dic['status']: return None
        asset_list = [asset_dic for asset_dic in all_asset_list if asset_dic['asset_ID'] == asset_info_id]
        logger.debug('SteamGridDB::get_assets() Total assets {} / Returned assets {}'.format(
            len(all_asset_list), len(asset_list)))

        return asset_list

    # SteamGridDB returns both the asset thumbnail URL and the full resolution URL so in
    # this scraper this method is trivial.
    def resolve_asset_URL(self, selected_asset, status_dic):
        url = selected_asset['url']
        return url, url

    def resolve_asset_URL_extension(self, selected_asset, image_url, status_dic):
        return io.get_URL_extension(image_url)

    def download_image(self, image_url, image_local_path: io.FileName):
        self._wait_for_API_request(100)
        # net_download_img() never prints URLs or paths.
        net.download_img(image_url, image_local_path)
        
        # failed? retry after 5 seconds
        if not image_local_path.exists():
            logger.debug('Download failed. Retry after 5 seconds')
            self._wait_for_API_request(5000)
            net.download_img(image_url, image_local_path)
        return image_local_path
           
    # --- Retrieve list of games ---
    def _search_candidates(self, search_term:str, platform:str, status_dic):
        # --- Retrieve JSON data with list of games ---
        search_string_encoded = quote_plus(search_term)
        url = '{}search/autocomplete/{}'.format(SteamGridDB.API_URL, search_string_encoded)
        
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('SteamGridDB_get_candidates.json', json_data)

        # --- Parse game list ---
        games_json = json_data['data']
        candidate_list = []
        for item in games_json:
            title = item['name']
            candidate = self._new_candidate_dic()
            candidate['id'] = item['id']
            candidate['display_name'] = title
            candidate['platform'] = platform
            candidate['scraper_platform'] = platform
            candidate['order'] = 1

            # Increase search score based on our own search.
            if title.lower() == search_term.lower():          candidate['order'] += 2
            if title.lower().find(search_term.lower()) != -1: candidate['order'] += 1
            candidate_list.append(candidate)

        # --- Sort game list based on the score. High scored candidates go first ---
        candidate_list.sort(key = lambda result: result['order'], reverse = True)

        return candidate_list

    # Get ALL available assets for game.
    # Cache all assets in the internal disk cache.
    def _retrieve_all_assets(self, candidate, status_dic):
        # --- Cache hit ---
        if self._check_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key):
            logger.debug('SteamGridDB._retrieve_all_assets() Internal cache hit "{0}"'.format(self.cache_key))
            return self._retrieve_from_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key)

        # --- Cache miss. Retrieve data and update cache ---
        logger.debug('SteamGridDB._retrieve_all_assets() Internal cache miss "{0}"'.format(self.cache_key))
               
        cover_assets = self._retrieve_cover_assets(candidate, status_dic)
        if not status_dic['status']: return None
        fanart_assets = self._retrieve_fanart_assets(candidate, status_dic)
        if not status_dic['status']: return None
        logo_assets = self._retrieve_logo_assets(candidate, status_dic)
        if not status_dic['status']: return None
        
        asset_list = cover_assets + fanart_assets + logo_assets
        logger.debug('SteamGridDB._retrieve_all_assets() A total of {0} assets found for candidate ID {1}'.format(
            len(asset_list), candidate['id']))

        # --- Put metadata in the cache ---
        logger.debug('SteamGridDB._retrieve_all_assets() Adding to internal cache "{0}"'.format(self.cache_key))
        self._update_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key, asset_list)

        return asset_list

    def _retrieve_cover_assets(self, candidate, status_dic):
        logger.debug('SteamGridDB._retrieve_cover_assets() Getting Covers...')
        url = '{}grids/game/{}'.format(SteamGridDB.API_URL, candidate['id'])
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('SteamGridDB_assets_covers.json', json_data)

        # --- Parse images page data ---
        asset_list = []
        for image_data in json_data['data']:
            style = image_data['style'] if 'style' in image_data else 'image'
            asset_data = self._new_assetdata_dic()
            asset_data['asset_ID'] = constants.ASSET_BOXFRONT_ID
            asset_data['display_name'] = "{} by {}".format(style, image_data['author']['name'])
            asset_data['url_thumb'] = image_data['thumb']
            asset_data['url'] = image_data['url']
            if self.verbose_flag: logger.debug('Found cover {0}'.format(asset_data['url_thumb']))
            asset_list.append(asset_data)
            
        logger.debug('SteamGridDB._retrieve_cover_assets() Found {} cover assets for candidate #{}'.format(
            len(asset_list), candidate['id']))

        return asset_list
    
    def _retrieve_logo_assets(self, candidate, status_dic):
        logger.debug('SteamGridDB._retrieve_logo_assets() Getting Logos...')
        url = '{}logos/game/{}'.format(SteamGridDB.API_URL, candidate['id'])
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('SteamGridDB_assets_logos.json', json_data)

        # --- Parse images page data ---
        asset_list = []
        for image_data in json_data['data']:
            style = image_data['style'] if 'style' in image_data else 'image'
            asset_data = self._new_assetdata_dic()
            asset_data['asset_ID'] = constants.ASSET_CLEARLOGO_ID
            asset_data['display_name'] = "{} by {}".format(style, image_data['author']['name'])
            asset_data['url_thumb'] = image_data['thumb']
            asset_data['url'] = image_data['url']
            if self.verbose_flag: logger.debug('Found logo {0}'.format(asset_data['url_thumb']))
            asset_list.append(asset_data)
            
        logger.debug('SteamGridDB._retrieve_logo_assets() Found {} logo assets for candidate #{}'.format(
            len(asset_list), candidate['id']))

        return asset_list
    
    def _retrieve_fanart_assets(self, candidate, status_dic):
        logger.debug('SteamGridDB._retrieve_fanart_assets() Getting Fanarts...')
        url = '{}heroes/game/{}'.format(SteamGridDB.API_URL, candidate['id'])
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('SteamGridDB_assets_fanarts.json', json_data)

        # --- Parse images page data ---
        asset_list = []
        for image_data in json_data['data']:
            style = image_data['style'] if 'style' in image_data else 'image'
            asset_data = self._new_assetdata_dic()
            asset_data['asset_ID'] = constants.ASSET_FANART_ID
            asset_data['display_name'] = "{} by {}".format(style, image_data['author']['name'])
            asset_data['url_thumb'] = image_data['thumb']
            asset_data['url'] = image_data['url']
            if self.verbose_flag: logger.debug('Found fanart {0}'.format(asset_data['url_thumb']))
            asset_list.append(asset_data)
            
        logger.debug('SteamGridDB._retrieve_fanart_assets() Found {} fanart assets for candidate #{}'.format(
            len(asset_list), candidate['id']))

        return asset_list

    # Retrieve URL and decode JSON object.
    # SteamGridDB API info https://www.steamgriddb.com/api/v2
    #
    # * When the API key is not configured or invalid SteamGridDB returns HTTP status code 401.
    def _retrieve_URL_as_JSON(self, url, status_dic, retry=0):
        self._wait_for_API_request(100)
        page_data_raw, http_code = net.get_URL(url, None, {"Authorization": "Bearer {}".format(self.api_key) })
        self.last_http_call = datetime.now()

        # --- Check HTTP error codes ---
        if http_code == 400:
            # Code 400 describes an error. See API description page.
            logger.debug('SteamGridDB._retrieve_URL_as_JSON() HTTP status 400: general error.')
            self._handle_error(status_dic, 'Bad HTTP status code {}'.format(http_code))
            return None
        elif http_code == 429 and retry < Scraper.RETRY_THRESHOLD:
            logger.debug('SteamGridDB._retrieve_URL_as_JSON() HTTP status 429: Limit exceeded.')
            # Number of requests limit, wait at least 2 minutes. Increments with every retry.
            amount_seconds = 120*(retry+1)
            wait_till_time = datetime.now() + timedelta(seconds=amount_seconds)
            kodi.dialog_OK('You\'ve exceeded the max rate limit.', 
                           'Respecting the website and we wait at least till {}.'.format(wait_till_time))
            self._wait_for_API_request(amount_seconds*1000)
            # waited long enough? Try again
            retry_after_wait = retry + 1
            return self._retrieve_URL_as_JSON(url, status_dic, retry_after_wait)
        elif http_code == 404:
            # Code 404 means the Game was not found. Return None but do not mark
            # error in status_dic.
            logger.debug('SteamGridDB._retrieve_URL_as_JSON() HTTP status 404: no candidates found.')
            return None
        elif http_code != 200:
            # Unknown HTTP status code.
            self._handle_error(status_dic, 'Bad HTTP status code {}'.format(http_code))
            return None
        
        # If page_data_raw is None at this point is because of an exception in net_get_URL()
        # which is not urllib2.HTTPError.
        if page_data_raw is None:
            self._handle_error(status_dic, 'Network error/exception in net_get_URL()')
            return None

        # Convert data to JSON.
        try:
            return json.loads(page_data_raw)
        except Exception as ex:
            logger.error('Error decoding JSON data from SteamGridDB.')
            self._handle_error(status_dic, 'Error decoding JSON data from SteamGridDB.')
            return None