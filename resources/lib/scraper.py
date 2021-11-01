# -*- coding: utf-8 -*-
#
# Advanced Emulator Launcher scraping engine for Screenscraper.

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
import base64
import zipfile
import time
from datetime import datetime, timedelta

from urllib.parse import quote_plus, quote

# --- AEL packages ---
from ael import constants, platforms, settings
from ael.utils import io, net, kodi
from ael.scrapers import Scraper

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------------------------
# ScreenScraper online scraper. Uses V2 API.
#
# | Site        | https://www.screenscraper.fr             |
# | API V1 docs | https://www.screenscraper.fr/webapi.php  |
# | API V2 docs | https://www.screenscraper.fr/webapi2.php |
#
# In the API documentation page some API function can be called as a test. Other test functions
# fail when called (invalid data, no user name/pass, etc.).
#
# * If no games are found with jeuInfos.php an HTTP status code 404 is returned.
# * If no platform (platform id = 0) is used ScreenScraper returns garbage, a totally unrelated
#   game to the one being searched. It is not advisable to use this scraper with a wrong
#   platform.
#
# ssuserInfos.php : Informations sur l'utilisateur ScreenScraper
# userlevelsListe.php : Liste des niveaux utilisateurs de ScreenScraper 
# nbJoueursListe.php : Liste des nombres de joueurs
# supportTypesListe.php : Liste des types de supports
# romTypesListe.php : Liste des types de roms
# genresListe.php : Liste des genres
# regionsListe.php : Liste des regions
# languesListe.php : Liste des langues
# classificationListe.php : Liste des Classification (Game Rating)
#
# mediaGroup.php : Téléchargement des médias images des groupes de jeux
# mediaCompagnie.php : Téléchargement des médias images des groupes de jeux
#
# systemesListe.php : Liste des systèmes / informations systèmes / informations médias systèmes
# mediaSysteme.php : Téléchargement des médias images des systèmes
# mediaVideoSysteme.php : Téléchargement des médias vidéos des systèmes
#
# jeuRecherche.php : Recherche d'un jeu avec son nom (retourne une table de jeux (limité a 30 jeux)
#                    classés par probabilité)
# jeuInfos.php : Informations sur un jeu / Médias d'un jeu
# mediaJeu.php : Téléchargement des médias images des jeux
# mediaVideoJeu.php : Téléchargement des médias vidéos des jeux
# mediaManuelJeu.php : Téléchargement des manuels des jeux
#
# botNote.php : Système pour l'automatisation d'envoi de note de jeu d'un membre ScreenScraper
# botProposition.php : Système pour automatisation d'envoi de propositions d'infos ou de médias
#                      a ScreenScraper
#
# >>> Liste des types d'infos textuelles pour les jeux (modiftypeinfo) <<<
# >>> Liste des types d'infos textuelles pour les roms (modiftypeinfo) <<<
#
# >>> Liste des types de média (regionsListe) <<<
# sstitle  Screenshot  Titre  png  obligatoire
# ss       Screenshot         png  obligatoire
# fanart   Fan Art            jpg
# ...
#
# --- API call examples ---
# * All API calls have parameters devid, devpassword, softname, output, ssid, sspassword
#   so I do not include them in the examples.
#
# * API call to get all game information. This API call return one game or fails.
#
#   https://www.screenscraper.fr/api/jeuInfos.php?
#   &crc=50ABC90A
#   &systemeid=1
#   &romtype=rom
#   &romnom=Sonic%20The%20Hedgehog%202%20(World).zip
#   &romtaille=749652
#   &gameid=1234 (Forces game, ROM info not necessary in this case).
#
# * API call to search for games:
#
#   https://www.screenscraper.fr/api/jeuRecherche.php?
#   &systemeid  (Optional)
#   &recherche  (Mandatory)
#
# ------------------------------------------------------------------------------------------------
class ScreenScraper(Scraper):
    # --- Class variables ------------------------------------------------------------------------
    supported_metadata_list = [
        constants.META_TITLE_ID,
        constants.META_YEAR_ID,
        constants.META_GENRE_ID,
        constants.META_DEVELOPER_ID,
        constants.META_NPLAYERS_ID,
        constants.META_ESRB_ID,
        constants.META_PLOT_ID,
    ]
    supported_asset_list = [
        constants.ASSET_FANART_ID,
        constants.ASSET_BANNER_ID,
        constants.ASSET_CLEARLOGO_ID,
        constants.ASSET_TITLE_ID,
        constants.ASSET_SNAP_ID,
        constants.ASSET_BOXFRONT_ID,
        constants.ASSET_BOXBACK_ID,
        constants.ASSET_3DBOX_ID,
        constants.ASSET_CARTRIDGE_ID,
        constants.ASSET_MAP_ID,
        # ASSET_MANUAL_ID,
        # ASSET_TRAILER_ID,
    ]
    # Unsupported AEL types:
    # manuel (Manual)
    # screenmarquee (Marquee with lower aspec ratio, more squared than rectangular).
    # box-2D-side (Box spine)
    # box-texture (Box front, spine and back combined).
    # support-texture (Cartridge/CD scan texture)
    # bezel-16-9 (Bezel for 16:9 horizontal monitors)
    # mixrbv1 (Mix recalbox Version 1)
    # mixrbv2 (Mix recalbox Version 2)
    asset_name_mapping = {
        'fanart'             : constants.ASSET_FANART_ID,
        'screenmarqueesmall' : constants.ASSET_BANNER_ID,
        'steamgrid'          : constants.ASSET_BANNER_ID,
        'wheel'              : constants.ASSET_CLEARLOGO_ID,
        'wheel-carbon'       : constants.ASSET_CLEARLOGO_ID,
        'wheel-steel'        : constants.ASSET_CLEARLOGO_ID,
        'sstitle'            : constants.ASSET_TITLE_ID,
        'ss'                 : constants.ASSET_SNAP_ID,
        'box-2D'             : constants.ASSET_BOXFRONT_ID,
        'box-2D-back'        : constants.ASSET_BOXBACK_ID,
        'box-3D'             : constants.ASSET_3DBOX_ID,
        'support-2D'         : constants.ASSET_CARTRIDGE_ID,
        'maps'               : constants.ASSET_MAP_ID,
    }

    # List of country/region suffixes supported by ScreenScraper.
    # Get list with API regionsListe.php call.
    # Items at the beginning will be searched first.
    # This code is automatically generated by script scrap_ScreenScraper_list_regions.py
    region_list = [
        'wor', # World
        'eu',  # Europe
        'us',  # USA
        'jp',  # Japan
        'ss',  # ScreenScraper
        'ame', # American continent
        'asi', # Asia
        'au',  # Australia
        'bg',  # Bulgaria
        'br',  # Brazil
        'ca',  # Canada
        'cl',  # Chile
        'cn',  # China
        'cus', # Custom
        'cz',  # Czech republic
        'de',  # Germany
        'dk',  # Denmark
        'fi',  # Finland
        'fr',  # France
        'gr',  # Greece
        'hu',  # Hungary
        'il',  # Israel
        'it',  # Italy
        'kr',  # Korea
        'kw',  # Kuwait
        'mor', # Middle East
        'nl',  # Netherlands
        'no',  # Norway
        'nz',  # New Zealand
        'oce', # Oceania
        'pe',  # Peru
        'pl',  # Poland
        'pt',  # Portugal
        'ru',  # Russia
        'se',  # Sweden
        'sk',  # Slovakia
        'sp',  # Spain
        'tr',  # Turkey
        'tw',  # Taiwan
        'uk',  # United Kingdom
    ]

    # This code is automatically generated by script scrap_ScreenScraper_list_languages.py
    language_list = [
        'en',  # English
        'es',  # Spanish
        'ja',  # Japanese
        'cz',  # Czech
        'da',  # Danish
        'de',  # German
        'fi',  # Finnish
        'fr',  # French
        'hu',  # Hungarian
        'it',  # Italian
        'ko',  # Korean
        'nl',  # Dutch
        'no',  # Norwegian
        'pl',  # Polish
        'pt',  # Portuguese
        'ru',  # Russian
        'sk',  # Slovak
        'sv',  # Swedish
        'tr',  # Turkish
        'zh',  # Chinese
    ]

    # This allows to change the API version easily.
    URL_jeuInfos            = 'https://www.screenscraper.fr/api2/jeuInfos.php'
    URL_jeuRecherche        = 'https://www.screenscraper.fr/api2/jeuRecherche.php'
    URL_image               = 'https://www.screenscraper.fr/image.php'
    URL_mediaJeu            = 'https://www.screenscraper.fr/api2/mediaJeu.php'

    URL_ssuserInfos         = 'https://www.screenscraper.fr/api2/ssuserInfos.php'
    URL_userlevelsListe     = 'https://www.screenscraper.fr/api2/userlevelsListe.php'
    URL_supportTypesListe   = 'https://www.screenscraper.fr/api2/supportTypesListe.php'
    URL_romTypesListe       = 'https://www.screenscraper.fr/api2/romTypesListe.php'
    URL_genresListe         = 'https://www.screenscraper.fr/api2/genresListe.php'
    URL_regionsListe        = 'https://www.screenscraper.fr/api2/regionsListe.php'
    URL_languesListe        = 'https://www.screenscraper.fr/api2/languesListe.php'
    URL_classificationListe = 'https://www.screenscraper.fr/api2/classificationListe.php'
    URL_systemesListe       = 'https://www.screenscraper.fr/api2/systemesListe.php'

    # Time to wait in get_assets() in seconds (float) to avoid scraper overloading.
    TIME_WAIT_GET_ASSETS = 1.2

    # --- Constructor ----------------------------------------------------------------------------
    def __init__(self):
        # --- This scraper settings ---
        self.dev_id       = 'V2ludGVybXV0ZTAxMTA='
        self.dev_pass     = 'VDlwU3J6akZCbWZRbWM4Yg=='
        self.softname     = settings.getSetting('scraper_screenscraper_AEL_softname')
        self.ssid         = settings.getSetting('scraper_screenscraper_ssid')
        self.sspassword   = settings.getSetting('scraper_screenscraper_sspass')
        self.region_idx   = settings.getSettingAsInt('scraper_screenscraper_region')
        self.language_idx = settings.getSettingAsInt('scraper_screenscraper_language')

        # --- Internal stuff ---
        self.last_get_assets_call = datetime.now()

        # Create list of regions to search stuff. Put the user preference first.
        self.user_region = ScreenScraper.region_list[self.region_idx]
        logger.debug('ScreenScraper.__init__() User preferred region "{}"'.format(self.user_region))

        # Create list of languages to search stuff. Put the user preference first.
        self.user_language = ScreenScraper.language_list[self.language_idx]
        logger.debug('ScreenScraper.__init__() User preferred language "{}"'.format(self.user_language))

        cache_dir = settings.getSetting('scraper_cache_dir')
        super(ScreenScraper, self).__init__(cache_dir)

    # --- Base class abstract methods ------------------------------------------------------------
    def get_name(self): return 'ScreenScraper'

    def get_filename(self): return 'ScreenScraper'

    def supports_disk_cache(self): return True

    def supports_search_string(self): return False

    def supports_metadata_ID(self, metadata_ID):
        return True if metadata_ID in ScreenScraper.supported_metadata_list else False

    def supports_metadata(self): return True

    def supports_asset_ID(self, asset_ID):
        return True if asset_ID in ScreenScraper.supported_asset_list else False

    def supports_assets(self): return True

    # ScreenScraper user login/password is mandatory. Actually, SS seems to work if no user
    # login/password is given, however it seems that the number of API requests is very
    # limited.
    def check_before_scraping(self, status_dic):
        if self.ssid and self.sspassword:
            logger.debug('ScreenScraper.check_before_scraping() ScreenScraper user name and pass OK.')
            return
        logger.error('ScreenScraper.check_before_scraping() ScreenScraper user name and/or pass not configured.')
        logger.error('ScreenScraper.check_before_scraping() Disabling ScreenScraper scraper.')
        self.scraper_deactivated = True
        status_dic['status'] = False
        status_dic['dialog'] = kodi.KODI_MESSAGE_DIALOG
        status_dic['msg'] = (
            'AEL requires your ScreenScraper user name and password. '
            'Create a user account in https://www.screenscraper.fr/ '
            'and set you user name and password in AEL addon settings.'
        )

    # _search_candidates_jeuInfos() uses the internal cache.
    # ScreenScraper uses the candidates and internal cache. It does not use the
    # medatada and asset caches at all because the metadata and assets are generated
    # with the internal cache.
    # Search term is always None for this scraper. rom_FN and ROM checksums are used
    # to search ROMs.
    def get_candidates(self, search_term:str, rom_FN:io.FileName, rom_checksums_FN:io.FileName, platform, status_dic):
        # If the scraper is disabled return None and do not mark error in status_dic.
        # Candidate will not be introduced in the disk cache and will be scraped again.
        if self.scraper_disabled:
            logger.debug('ScreenScraper.get_candidates() Scraper disabled. Returning empty data.')
            return None

        # Prepare data for scraping.
        rombase = rom_FN.getBase()
        rompath = rom_FN.getPath()
        romchecksums_path = rom_checksums_FN.getPath() if rom_checksums_FN is not None else None
        scraper_platform = convert_AEL_platform_to_ScreenScraper(platform)

        # --- Get candidates ---
        # ScreenScraper jeuInfos.php returns absolutely everything about a single ROM, including
        # metadata, artwork, etc. jeuInfos.php returns one game or nothing at all.
        # ScreenScraper returns only one game or nothing at all.
        logger.debug('ScreenScraper.get_candidates() rompath      "{}"'.format(rompath))
        logger.debug('ScreenScraper.get_candidates() romchecksums "{}"'.format(romchecksums_path))
        logger.debug('ScreenScraper.get_candidates() AEL platform "{}"'.format(platform))
        logger.debug('ScreenScraper.get_candidates() SS platform  "{}"'.format(scraper_platform))
        candidate_list = self._search_candidates_jeuInfos(
            rom_FN, rom_checksums_FN, platform, scraper_platform, status_dic)
        # _search_candidates_jeuRecherche() does not work for get_metadata() and get_assets()
        # because jeu_dic is not introduced in the internal cache.
        # candidate_list = self._search_candidates_jeuRecherche(
        #     search_term, rombase_noext, platform, scraper_platform, status_dic)
        if not status_dic['status']: return None

        return candidate_list

    # This function may be called many times in the ROM Scanner. All calls to this function
    # must be cached. See comments for this function in the Scraper abstract class.
    def get_metadata(self, status_dic):
        # --- If scraper is disabled return immediately and silently ---
        if self.scraper_disabled:
            logger.debug('ScreenScraper.get_metadata() Scraper disabled. Returning empty data.')
            return self._new_gamedata_dic()

        # --- Retrieve jeu_dic from internal cache ---
        if self._check_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key):
            logger.debug('ScreenScraper.get_metadata() Internal cache hit "{}"'.format(self.cache_key))
            jeu_dic = self._retrieve_from_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key)
        else:
            raise ValueError('Logic error')

        # --- Parse game metadata ---
        gamedata = self._new_gamedata_dic()
        gamedata['title']     = self._parse_meta_title(jeu_dic)
        gamedata['year']      = self._parse_meta_year(jeu_dic)
        gamedata['genre']     = self._parse_meta_genre(jeu_dic)
        gamedata['developer'] = self._parse_meta_developer(jeu_dic)
        gamedata['nplayers']  = self._parse_meta_nplayers(jeu_dic)
        gamedata['esrb']      = self._parse_meta_esrb(jeu_dic)
        gamedata['plot']      = self._parse_meta_plot(jeu_dic)

        return gamedata

    # This function may be called many times in the ROM Scanner. All calls to this function
    # must be cached. See comments for this function in the Scraper abstract class.
    def get_assets(self, asset_info_id:str, status_dic):
        # --- If scraper is disabled return immediately and silently ---
        if self.scraper_disabled:
            logger.debug('ScreenScraper.get_assets() Scraper disabled. Returning empty data.')
            return []

        logger.debug('ScreenScraper.get_assets() Getting assets {} for candidate ID = {}'.format(
            asset_info_id, self.candidate['id']))

        # --- Retrieve jeu_dic from internal cache ---
        if self._check_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key):
            logger.debug('ScreenScraper.get_assets() Internal cache hit "{}"'.format(self.cache_key))
            jeu_dic = self._retrieve_from_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key)
        else:
            raise ValueError('Logic error')

        # --- Parse game assets ---
        all_asset_list = self._retrieve_all_assets(jeu_dic, status_dic)
        if not status_dic['status']: return None
        asset_list = [asset_dic for asset_dic in all_asset_list if asset_dic['asset_ID'] == asset_info_id]
        logger.debug('ScreenScraper.get_assets() Total assets {} / Returned assets {}'.format(
            len(all_asset_list), len(asset_list)))

        # Wait some time to avoid scraper overloading.
        # As soon as we return from get_assets() the ROM scanner quickly chooses one
        # asset and start the download. Then, get_assets() is called again with different
        # asset_ID. Make sure we wait some time here so there is some time between asset
        # download to not overload ScreenScraper.
        self._wait_for_asset_request()

        return asset_list

    # Sometimes ScreenScraper URLs have spaces. One example is the map images of Genesis Sonic 1.
    # https://www.screenscraper.fr/gameinfos.php?plateforme=1&gameid=5
    # Make sure to escape the spaces in the returned URL.
    def resolve_asset_URL(self, selected_asset, status_dic):
        # For some reason this code does not work well...
        # url = selected_asset['url']
        # if url.startswith('http://'):    return 'http://' + urllib.quote(url[7:])
        # elif url.startswith('https://'): return 'https://' + urllib.quote(url[8:])
        # else:                            raise ValueError
        url = selected_asset['url']
        url_log = self._clean_URL_for_log(url)

        return url, url_log

    def resolve_asset_URL_extension(self, selected_asset, url, status_dic):
        return selected_asset['SS_format']

    # --- This class own methods -----------------------------------------------------------------
    def debug_get_user_info(self, status_dic):
        logger.debug('ScreenScraper.debug_get_user_info() Geting SS user info...')
        url = ScreenScraper.URL_ssuserInfos + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_user_info.json', json_data)

        return json_data

    def debug_get_user_levels(self, status_dic):
        logger.debug('ScreenScraper.debug_get_user_levels() Geting SS user level list...')
        url = ScreenScraper.URL_userlevelsListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_user_level_list.json', json_data)

        return json_data

    # nbJoueursListe.php : Liste des nombres de joueurs 
    # This function not coded at the moment.

    def debug_get_support_types(self, status_dic):
        logger.debug('ScreenScraper.debug_get_support_types() Geting SS Support Types list...')
        url = ScreenScraper.URL_supportTypesListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_support_types_list.json', json_data)

        return json_data

    def debug_get_ROM_types(self, status_dic):
        logger.debug('ScreenScraper.debug_get_ROM_types() Geting SS ROM types list...')
        url = ScreenScraper.URL_romTypesListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_ROM_types_list.json', json_data)

        return json_data

    def debug_get_genres(self, status_dic):
        logger.debug('ScreenScraper.debug_get_genres() Geting SS Genre list...')
        url = ScreenScraper.URL_genresListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_genres_list.json', json_data)

        return json_data

    def debug_get_regions(self, status_dic):
        logger.debug('ScreenScraper.debug_get_regions() Geting SS Regions list...')
        url = ScreenScraper.URL_regionsListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_regions_list.json', json_data)

        return json_data

    def debug_get_languages(self, status_dic):
        logger.debug('ScreenScraper.debug_get_languages() Geting SS Languages list...')
        url = ScreenScraper.URL_languesListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_language_list.json', json_data)

        return json_data

    def debug_get_clasifications(self, status_dic):
        logger.debug('ScreenScraper.debug_get_clasifications() Geting SS Clasifications list...')
        url = ScreenScraper.URL_classificationListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_clasifications_list.json', json_data)

        return json_data

    def debug_get_platforms(self, status_dic):
        logger.debug('ScreenScraper.debug_get_platforms() Getting SS platforms...')
        url = ScreenScraper.URL_systemesListe + self._get_common_SS_URL()
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_get_platform_list.json', json_data)

        return json_data

    # Debug test function for jeuRecherche.php (game search).
    def debug_game_search(self, search_term, rombase_noext, platform, status_dic):
        logger.debug('ScreenScraper.debug_game_search() Calling jeuRecherche.php...')
        scraper_platform = convert_AEL_platform_to_ScreenScraper(platform)
        system_id = scraper_platform
        recherche = quote(rombase_noext)
        logger.debug('ScreenScraper.debug_game_search() system_id  "{}"'.format(system_id))
        logger.debug('ScreenScraper.debug_game_search() recherche  "{}"'.format(recherche))

        url_tail = '&systemeid={}&recherche={}'.format(system_id, recherche)
        url = ScreenScraper.URL_jeuRecherche + self._get_common_SS_URL() + url_tail
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if json_data is None or not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_gameSearch.json', json_data)

    # Call to ScreenScraper jeuInfos.php.
    def _search_candidates_jeuInfos(self, rom_FN, rom_checksums_FN, platform, scraper_platform, status_dic):
        if rom_FN is None or rom_checksums_FN is None:
            logger.warning('Trying to scrape a non existing or virtual ROM file with Screenscraper')
            return None
        
        # --- Test data ---
        # * Example from ScreenScraper API info page.
        #   #crc=50ABC90A&systemeid=1&romtype=rom&romnom=Sonic%20The%20Hedgehog%202%20(World).zip&romtaille=749652
        # * Note that if the CRC is all zeros and the filesize also 0 it seems to work.
        #   Also, if no file extension is passed it seems to work. Looks like SS is capable of
        #   fuzzy searches to some degree.
        # * If rom_type = 'rom' SS returns gargabe for CD-based platforms like Playstation.

        # ISO-based platform set.
        # This must be moved somewhere else...
        ISO_platform_set = set([
            'Fujitsu FM Towns Marty',
            'NEC PC Engine CDROM2',
            'NEC TurboGrafx CD',
            'Nintendo GameCube',
            'Nintendo Wii',
            'Sega Dreamcast',
            'Sega Saturn',
            'Sony PlayStation',
            'Sony PlayStation 2',
            'Sony PlayStation Portable',
        ])

        # --- IMPORTANT ---
        # ScreenScraper requires all CRC, MD5 and SHA1 and the correct file size of the
        # files scraped.
        if self.debug_checksums_flag:
            # Use fake checksums when developing the scraper with fake 0-sized files.
            logger.info('Using debug checksums and not computing real ones.')
            checksums = {
                'crc'  : self.debug_crc, 'md5'  : self.debug_md5, 'sha1' : self.debug_sha1,
                'size' : self.debug_size, 'rom_name' : rom_FN.getBase(),
            }
        else:
            checksums = self._get_SS_checksum(rom_checksums_FN)
            if checksums is None:
                status_dic['status'] = False
                status_dic['msg'] = 'Error computing file checksums.'
                return None

        # --- Actual data for scraping in AEL ---
        # Change rom_type for ISO-based platforms
        rom_type = 'iso' if platform in ISO_platform_set else 'rom'
        system_id = scraper_platform
        crc_str = checksums['crc']
        md5_str = checksums['md5']
        sha1_str = checksums['sha1']
        # rom_name = urllib.quote(checksums['rom_name'])
        rom_name = quote_plus(checksums['rom_name'])
        rom_size = checksums['size']
        # logger.debug('ScreenScraper._search_candidates_jeuInfos() ssid       "{}"'.format(self.ssid))
        # logger.debug('ScreenScraper._search_candidates_jeuInfos() ssid       "{}"'.format('***'))
        # logger.debug('ScreenScraper._search_candidates_jeuInfos() sspassword "{}"'.format(self.sspassword))
        # logger.debug('ScreenScraper._search_candidates_jeuInfos() sspassword "{}"'.format('***'))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() rom_type   "{}"'.format(rom_type))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() system_id  "{}"'.format(system_id))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() crc_str    "{}"'.format(crc_str))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() md5_str    "{}"'.format(md5_str))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() sha1_str   "{}"'.format(sha1_str))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() rom_name   "{}"'.format(rom_name))
        logger.debug('ScreenScraper._search_candidates_jeuInfos() rom_size   "{}"'.format(rom_size))

        # --- Build URL and retrieve JSON ---
        url_tail = '&romtype={}&systemeid={}&crc={}&md5={}&sha1={}&romnom={}&romtaille={}'.format(
            rom_type, system_id, crc_str, md5_str, sha1_str, rom_name, rom_size)
        url = ScreenScraper.URL_jeuInfos + self._get_common_SS_URL() + url_tail
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        # If status_dic mark an error there was an exception. Return None.
        if not status_dic['status']: return None
        # If no games were found status_dic['status'] is True and json_data is None.
        # Return empty list of candidates.
        if json_data is None: return []
        self._dump_json_debug('ScreenScraper_gameInfo.json', json_data)

        # --- Print some info ---
        jeu_dic = json_data['response']['jeu']
        id_str = str(jeu_dic['id'])
        title = jeu_dic['noms'][0]['text']
        logger.debug('Game "{}" (ID {})'.format(title, id_str))
        logger.debug('Number of ROMs {} / Number of assets {}'.format(
            len(jeu_dic['roms']), len(jeu_dic['medias'])))

        # --- Build candidate_list from ScreenScraper jeu_dic returned by jeuInfos.php ---
        # SS returns one candidate or no candidate.
        candidate = self._new_candidate_dic()
        candidate['id'] = id_str
        candidate['display_name'] = title
        candidate['platform'] = platform
        candidate['scraper_platform'] = scraper_platform
        candidate['order'] = 1

        # --- Add candidate jeu_dic to the internal cache ---
        logger.debug('ScreenScraper._search_candidates_jeuInfos() Adding to internal cache "{}"'.format(
            self.cache_key))
        # IMPORTANT Do not clean URLs. There could be problems reconstructing some URLs.
        # self._clean_JSON_for_dumping(jeu_dic)
        # Remove the ROM information to decrease the size of the SS internal cache.
        # ROM information in SS is huge.
        jeu_dic['roms'] = []
        self._update_disk_cache(Scraper.CACHE_INTERNAL, self.cache_key, jeu_dic)

        return [ candidate ]

    # Call to ScreenScraper jeuRecherche.php.
    # Not used at the moment, just here for research.
    def _search_candidates_jeuRecherche(self, search_term, rombase_noext, platform, scraper_platform, status_dic):
        # --- Actual data for scraping in AEL ---
        logger.debug('ScreenScraper._search_candidates_jeuRecherche() Calling jeuRecherche.php...')
        scraper_platform = convert_AEL_platform_to_ScreenScraper(platform)
        system_id = scraper_platform
        recherche = quote_plus(rombase_noext)
        logger.debug('ScreenScraper._search_candidates_jeuRecherche() system_id  "{}"'.format(system_id))
        logger.debug('ScreenScraper._search_candidates_jeuRecherche() recherche  "{}"'.format(recherche))

        # --- Build URL and retrieve JSON ---
        url_tail = '&systemeid={}&recherche={}'.format(system_id, recherche)
        url = ScreenScraper.URL_jeuRecherche + self._get_common_SS_URL() + url_tail
        json_data = self._retrieve_URL_as_JSON(url, status_dic)
        if json_data is None or not status_dic['status']: return None
        self._dump_json_debug('ScreenScraper_gameSearch.json', json_data)

        # * If no games were found server replied with a HTTP 404 error. json_data is None and
        #  status_dic signals operation succesfull. Return empty list of candidates.
        # * If an error/exception happened then it is marked in status_dic.
        if json_data is None: return []
        jeu_list = json_data['response']['jeux']
        logger.debug('Number of games {}'.format(len(jeu_list)))

        # --- Build candidate_list ---
        # cache_key = search_term + '__' + rombase_noext + '__' + platform
        candidate_list = []
        for jeu_dic in jeu_list:
            id_str = jeu_dic['id']
            title = jeu_dic['noms'][0]['text']
            candidate = self._new_candidate_dic()
            candidate['id'] = id_str
            candidate['display_name'] = title
            candidate['platform'] = platform
            candidate['scraper_platform'] = scraper_platform
            candidate['order'] = 1
            # candidate['SS_cache_str'] = cache_key # Special field to retrieve game from SS cache.
            candidate_list.append(candidate)

        # --- Add candidate games to the internal cache ---
        # logger.debug('ScreenScraper._search_candidates_jeuInfos() Adding to internal cache')
        # self.cache_jeuInfos[cache_key] = jeu_dic

        return candidate_list

    def _parse_meta_title(self, jeu_dic):
        try:
            # First search for the user preferred region.
            for n in jeu_dic['noms']:
                if n['region'] == self.user_region: return n['text']
            # If nothing found then search in the sorted list of regions.
            for region in ScreenScraper.region_list:
                for n in jeu_dic['noms']:
                    if n['region'] == region: return n['text']
        except KeyError:
            pass

        return constants.DEFAULT_META_TITLE

    def _parse_meta_year(self, jeu_dic):
        try:
            for n in jeu_dic['dates']:
                if n['region'] == self.user_region: return n['text'][0:4]
            for region in ScreenScraper.region_list:
                for n in jeu_dic['dates']:
                    if n['region'] == region: return n['text'][0:4]
        except KeyError:
            pass

        return constants.DEFAULT_META_YEAR

    # Use first genre only for now.
    def _parse_meta_genre(self, jeu_dic):
        try:
            genre_item = jeu_dic['genres'][0]
            for n in genre_item['noms']:
                if n['langue'] == self.user_language: return n['text']
            for language in ScreenScraper.language_list:
                for n in genre_item['noms']:
                    if n['langue'] == language: return n['text']
        except KeyError:
            pass

        return constants.DEFAULT_META_GENRE

    def _parse_meta_developer(self, jeu_dic):
        try:
            return jeu_dic['developpeur']['text']
        except KeyError:
            pass

        return constants.DEFAULT_META_DEVELOPER

    def _parse_meta_nplayers(self, jeu_dic):
        # EAFP Easier to ask for forgiveness than permission.
        try:
            return jeu_dic['joueurs']['text']
        except KeyError:
            pass

        return constants.DEFAULT_META_NPLAYERS

    # Do not working at the moment.
    def _parse_meta_esrb(self, jeu_dic):
        # if 'classifications' in jeu_dic and 'ESRB' in jeu_dic['classifications']:
        #     return jeu_dic['classifications']['ESRB']

        return constants.DEFAULT_META_ESRB

    def _parse_meta_plot(self, jeu_dic):
        try:
            for n in jeu_dic['synopsis']:
                if n['langue'] == self.user_language: return n['text']
            for language in ScreenScraper.language_list:
                for n in jeu_dic['synopsis']:
                    if n['langue'] == language: return n['text']
        except KeyError:
            pass

        return constants.DEFAULT_META_PLOT

    # Get ALL available assets for game. Returns all assets found in the jeu_dic dictionary.
    # It is not necessary to cache this function because all the assets can be easily
    # extracted from jeu_dic.
    #
    # For now assets do not support region or language settings. I plan to match ROM
    # Language and Region with ScreenScraper Language and Region soon. For example, if we
    # are scraping a Japan ROM we must get the Japan artwork and not other region artwork.
    #
    # Examples:
    # https://www.screenscraper.fr/gameinfos.php?gameid=5     # Sonic 1 Megadrive
    # https://www.screenscraper.fr/gameinfos.php?gameid=3     # Sonic 2 Megadrive
    # https://www.screenscraper.fr/gameinfos.php?gameid=1187  # Sonic 3 Megadrive
    # https://www.screenscraper.fr/gameinfos.php?gameid=19249 # Final Fantasy VII PSX
    #
    # Example of download and thumb URLs. Thumb URLs are used to display media in the website:
    # https://www.screenscraper.fr/image.php?gameid=5&media=sstitle&hd=0&region=wor&num=&version=&maxwidth=338&maxheight=190
    # https://www.screenscraper.fr/image.php?gameid=5&media=fanart&hd=0&region=&num=&version=&maxwidth=338&maxheight=190
    # https://www.screenscraper.fr/image.php?gameid=5&media=steamgrid&hd=0&region=&num=&version=&maxwidth=338&maxheight=190
    #
    # TODO: support Manuals and Trailers.
    # TODO: match ROM region and ScreenScraper region.
    def _retrieve_all_assets(self, jeu_dic, status_dic):
        asset_list = []
        medias_list = jeu_dic['medias']
        for media_dic in medias_list:
            # Find known asset types. ScreenScraper has really a lot of different assets.
            if media_dic['type'] in ScreenScraper.asset_name_mapping:
                asset_ID = ScreenScraper.asset_name_mapping[media_dic['type']]
            else:
                # Skip unknwon assets
                continue

            # Build thumb URL
            game_ID = jeu_dic['id']
            region = media_dic['region'] if 'region' in media_dic else ''
            if region: media_type = media_dic['type'] + ' ' + region
            else:      media_type = media_dic['type']
            url_thumb_b = '?gameid={}&media={}&region={}'.format(game_ID, media_type, region)
            url_thumb_c = '&hd=0&num=&version=&maxwidth=338&maxheight=190'
            url_thumb = ScreenScraper.URL_image + url_thumb_b + url_thumb_c

            # Build asset URL. ScreenScraper URLs are stripped down when saved to the cache
            # to save space and time. FEATURE CANCELED. There could be problems reconstructing
            # some URLs and the space saved is not so great for most games.
            # systemeid = jeu_dic['systemeid']
            # media = '{}({})'.format(media_type, region)
            # url_b = '?devid={}&devpassword={}&softname={}&ssid={}&sspassword={}'.format(
            #     base64.b64decode(self.dev_id), base64.b64decode(self.dev_pass),
            #     self.softname, self.ssid, self.sspassword)
            # url_c = '&systemeid={}&jeuid={}&media={}'.format(systemeid, game_ID, media)
            # url_asset = ScreenScraper.URL_mediaJeu + url_b + url_c
            # logger.debug('URL "{}"'.format(url_asset))

            # Create asset dictionary
            asset_data = self._new_assetdata_dic()
            asset_data['asset_ID'] = asset_ID
            asset_data['display_name'] = media_type
            asset_data['url_thumb'] = str(url_thumb)
            asset_data['url'] = media_dic['url']
            # Special ScreenScraper field to resolve URL extension later.
            asset_data['SS_format'] = media_dic['format']
            asset_list.append(asset_data)

        return asset_list

    # 1) If rom_checksums_FN is a ZIP file and contains one and only one file, then consider that
    #    file the ROM, decompress in memory and calculate the checksums.
    # 2) If rom_checksums_FN is a standard file or 1) fails then calculate the checksums of
    #    the file.
    # 3) Return a checksums dictionary if everything is OK. Return None in case of any error.
    def _get_SS_checksum(self, rom_checksums_FN:io.FileName):
              
        f_basename = rom_checksums_FN.getBase()
        f_path = rom_checksums_FN.getPath()
        logger.debug('_get_SS_checksum() Processing "{}"'.format(f_path))
        if f_basename.lower().endswith('.zip'):
            logger.debug('_get_SS_checksum() ZIP file detected.')
            if not zipfile.is_zipfile(f_path):
                logger.error('zipfile.is_zipfile() returns False. Bad ZIP file.')
                return None
            else:
                logger.debug('_get_SS_checksum() ZIP file seems to be correct.')
            zip = zipfile.ZipFile(f_path)
            namelist = zip.namelist()
            # log_variable('namelist', namelist)
            if len(namelist) == 1:
                logger.debug('_get_SS_checksum() ZIP file has one file only.')
                logger.debug('_get_SS_checksum() Decompressing file "{}"'.format(namelist[0]))
                file_bytes = zip.read(namelist[0])
                logger.debug('_get_SS_checksum() Decompressed size is {} bytes'.format(len(file_bytes)))
                checksums = io.misc_calculate_stream_checksums(file_bytes)
                checksums['rom_name'] = namelist[0]
                logger.debug('_get_SS_checksum() ROM name is "{}"'.format(checksums['rom_name']))
                return checksums
            else:
                logger.debug('_get_SS_checksum() ZIP file has {} files.'.format(len(namelist)))
                logger.debug('_get_SS_checksum() Computing checksum of whole ZIP file.')
        else:
            logger.debug('_get_SS_checksum() File is not ZIP. Computing checksum of whole file.')
        # Otherwise calculate checksums of the whole file
        checksums = io.misc_calculate_checksums(rom_checksums_FN)
        if checksums:
            checksums['rom_name'] = f_basename
            logger.debug('_get_SS_checksum() ROM name is "{}"'.format(checksums['rom_name']))

        return checksums

    # ScreenScraper URLs have the developer password and the user password.
    # Clean URLs for safe logging.
    def _clean_URL_for_log(self, url):
        # --- Keep things simple! ---
        clean_url = url
        # --- Basic cleaning ---
        # clean_url = re.sub('devid=[^&]*&', 'devid=***&', clean_url)
        # clean_url = re.sub('devpassword=[^&]*&', 'devpassword=***&', clean_url)
        # clean_url = re.sub('ssid=[^&]*&', 'ssid=***&', clean_url)
        # clean_url = re.sub('sspassword=[^&]*&', 'sspassword=***&', clean_url)
        # clean_url = re.sub('sspassword=[^&]*$', 'sspassword=***', clean_url)
        # --- Mr Propoer. SS URLs are very long ---
        clean_url = re.sub('devid=[^&]*&', '', clean_url)
        clean_url = re.sub('devid=[^&]*$', '', clean_url)
        clean_url = re.sub('devpassword=[^&]*&', '', clean_url)
        clean_url = re.sub('devpassword=[^$]*$', '', clean_url)
        clean_url = re.sub('softname=[^&]*&', '', clean_url)
        clean_url = re.sub('softname=[^&]*$', '', clean_url)
        clean_url = re.sub('output=[^&]*&', '', clean_url)
        clean_url = re.sub('output=[^&]*$', '', clean_url)
        clean_url = re.sub('ssid=[^&]*&', '', clean_url)
        clean_url = re.sub('ssid=[^&]*$', '', clean_url)
        clean_url = re.sub('sspassword=[^&]*&', '', clean_url)
        clean_url = re.sub('sspassword=[^&]*$', '', clean_url)

        # log_variable('url', url)
        # log_variable('clean_url', clean_url)

        return clean_url

    # Reimplementation of base class method.
    # ScreenScraper needs URL cleaning in JSON before dumping because URL have passwords.
    # Only clean data if JSON file is dumped.
    def _dump_json_debug(self, file_name, json_data):
        if not self.dump_file_flag: return
        json_data_clean = self._clean_JSON_for_dumping(json_data)
        super(ScreenScraper, self)._dump_json_debug(file_name, json_data_clean)

    # JSON recursive iterator generator. Keeps also track of JSON keys.
    # yield from added in Python 3.3
    # https://stackoverflow.com/questions/38397285/iterate-over-all-items-in-json-object
    # https://stackoverflow.com/questions/14692690/access-nested-dictionary-items-via-a-list-of-keys
    def _recursive_iter(self, obj, keys = ()):
        if isinstance(obj, dict):
            for k, v in obj.items():
                # yield from self._recursive_iter(item)
                for k_t, v_t in self._recursive_iter(v, keys + (k,)):
                    yield k_t, v_t
        elif any(isinstance(obj, t) for t in (list, tuple)):
            for idx, item in enumerate(obj):
                # yield from recursive_iter(item, keys + (idx,))
                for k_t, v_t in self._recursive_iter(item, keys + (idx,)):
                    yield k_t, v_t
        else:
            yield keys, obj

    # Get a given data from a dictionary with position provided as a list (iterable)
    # Example maplist = ["b", "v", "y"] or ("b", "v", "y")
    def _getFromDict(self, dataDict, mapList):
        for k in mapList: dataDict = dataDict[k]

        return dataDict

    # Recursively cleans URLs in a JSON data structure for safe JSON file data dumping.
    def _clean_JSON_for_dumping(self, json_data):
        # --- Recursively iterate data ---
        # Do not modify dictionary when it is recursively iterated.
        URL_key_list = []
        logger.debug('ScreenScraper._clean_JSON_for_dumping() Cleaning JSON URLs.')
        for keys, item in self._recursive_iter(json_data):
            # logger.debug('{} "{}"'.format(keys, item))
            # logger.debug('Type item "{}"'.format(type(item)))
            # Skip non string objects.
            if not isinstance(item, str): continue
            if item.startswith('http'):
                # logger.debug('Adding URL "{}"'.format(item))
                URL_key_list.append(keys)

        # --- Do the actual cleaning ---
        for keys in URL_key_list:
            # logger.debug('Cleaning "{}"'.format(keys))
            url = self._getFromDict(json_data, keys)
            clean_url = self._clean_URL_for_log(url)
            # logger.debug('Cleaned  "{}"'.format(clean_url))
            self._setInDict(json_data, keys, clean_url)
        logger.debug('ScreenScraper._clean_JSON_for_dumping() Cleaned {} URLs'.format(len(URL_key_list)))

    # Set a given data in a dictionary with position provided as a list (iterable)
    def _setInDict(self, dataDict, mapList, value):
        for k in mapList[:-1]: dataDict = dataDict[k]
        dataDict[mapList[-1]] = value

    # Retrieve URL and decode JSON object.
    #
    # * When the API user/pass is not configured or invalid SS returns ...
    # * When the API number of calls is exhausted SS returns a HTTP 429 error code.
    # * When the API number of calls for the whole day is exhausted SS returns HTTP status code 430.
    #   In this case mark error in status_dic and return None.
    # * In case of any error/exception mark error in status_dic and return None.
    # * When the a game search is not succesfull SS returns a "HTTP Error 404: Not Found" error.
    #   In this case status_dic marks no error and return None.
    def _retrieve_URL_as_JSON(self, url, status_dic, retry=0):
        self._wait_for_API_request(2000)
        page_data_raw, http_code = net.get_URL(url, self._clean_URL_for_log(url))
        self.last_http_call = datetime.now()

        # --- Check HTTP error codes ---
        if http_code == 400:
            # Code 400 describes an error. See API description page.
            logger.debug('ScreenScraper._retrieve_URL_as_JSON() HTTP status 400: general error.')
            self._handle_error(status_dic, 'Bad HTTP status code {}'.format(http_code))
            return None
        elif http_code == 429 and retry < Scraper.RETRY_THRESHOLD:
            logger.debug('ScreenScraper._retrieve_URL_as_JSON() HTTP status 429: Limit exceeded.')
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
            # Code 404 in SS means the ROM was not found. Return None but do not mark
            # error in status_dic.
            logger.debug('ScreenScraper._retrieve_URL_as_JSON() HTTP status 404: no candidates found.')
            return None
        elif http_code != 200:
            # Unknown HTTP status code.
            self._handle_error(status_dic, 'Bad HTTP status code {}'.format(http_code))
            return None
        # self._dump_file_debug('ScreenScraper_data_raw.txt', page_data_raw)

        # If page_data_raw is None at this point is because of an exception in net_get_URL()
        # which is not urllib2.HTTPError.
        if page_data_raw is None:
            self._handle_error(status_dic, 'Network error/exception in net_get_URL()')
            return None

        # Convert data to JSON.
        try:
            return json.loads(page_data_raw)
        except Exception as ex:
            logger.error('Error decoding JSON data from ScreenScraper.')

        # This point is reached if there was an exception decoding JSON.
        # Sometimes ScreenScraper API V2 returns badly formatted JSON. Try to fix this.
        # See https://github.com/muldjord/skyscraper/blob/master/src/screenscraper.cpp
        # The badly formatted JSON is at the end of the file, for example:
        #			],     <----- Here it should be a ']' and not '],'.
        #		}
        #	}
        #}
        logger.error('Trying to repair ScreenScraper raw data (Try 1).')
        new_page_data_raw = page_data_raw.replace('],\n\t\t}', ']\n\t\t}')
        try:
            return json.loads(new_page_data_raw)
        except Exception as ex:
            logger.error('Error decoding JSON data from ScreenScraper (Try 1).')

        # At the end of the JSON data file...
        #		},         <----- Here it should be a '}' and not '},'.
        #		}
        #	}
        #            
        logger.error('Trying to repair ScreenScraper raw data (Try 2).')
        new_page_data_raw = page_data_raw.replace('\t\t},\n\t\t}', '\t\t}\n\t\t}')
        try:
            return json.loads(new_page_data_raw)
        except Exception as ex:
            logger.error('Error decoding JSON data from ScreenScraper (Try 2).')
            logger.error('Cannot decode JSON (invalid JSON returned). Dumping debug files...')
            scraper_cache_fn = io.FileName(self.scraper_cache_dir)
            file_path = scraper_cache_fn.pjoin('ScreenScraper_url.txt')
            file_path.writeAll(url)
            
            file_path = scraper_cache_fn.pjoin('ScreenScraper_page_data_raw.txt')
            file_path.writeAll(page_data_raw)
            
            self._handle_exception(ex, status_dic,
                'Error decoding JSON data from ScreenScraper (fixed version).')
            return None

    # All ScreenScraper URLs must have this arguments.
    def _get_common_SS_URL(self):
        url_SS = '?devid={}&devpassword={}&softname={}&output=json&ssid={}&sspassword={}'.format(
            base64.b64decode(self.dev_id).decode('utf-8'), base64.b64decode(self.dev_pass).decode('utf-8'),
            self.softname, self.ssid, self.sspassword)

        return url_SS

    # If less than TIME_WAIT_GET_ASSETS seconds have passed since the last call
    # to this function then wait TIME_WAIT_GET_ASSETS seconds.
    def _wait_for_asset_request(self):
        now = datetime.now()
        seconds_since_last_call = (now - self.last_get_assets_call).total_seconds()
        if seconds_since_last_call < ScreenScraper.TIME_WAIT_GET_ASSETS:
            logger.debug('SS._wait_for_asset_request() Sleeping to avoid overloading...')
            time.sleep(ScreenScraper.TIME_WAIT_GET_ASSETS)
        # Update waiting time for next call.
        self.last_get_assets_call = datetime.now()
        

# ------------------------------------------------------------------------------------------------
# Screenscraper supported platforms mapped to AEL platforms.
# ------------------------------------------------------------------------------------------------
DEFAULT_PLAT_SCREENSCRAPER = 0
def convert_AEL_platform_to_ScreenScraper(platform_long_name):
    matching_platform = platforms.get_AEL_platform(platform_long_name)
    if matching_platform.compact_name in AEL_compact_platform_Screenscraper_mapping:
        return AEL_compact_platform_Screenscraper_mapping[matching_platform.compact_name]
    
    if matching_platform.aliasof is not None and matching_platform.aliasof in AEL_compact_platform_Screenscraper_mapping:
        return AEL_compact_platform_Screenscraper_mapping[matching_platform.aliasof]
        
    # Platform not found.
    return DEFAULT_PLAT_SCREENSCRAPER

def convert_Screenscraper_platform_to_AEL_platform(self, screenscraper_platform):
    if screenscraper_platform in Screenscraper_AEL_compact_platform_mapping:
        platform_compact_name = Screenscraper_AEL_compact_platform_mapping[screenscraper_platform]
        return platforms.get_AEL_platform_by_compact(platform_compact_name)
        
    return platforms.get_AEL_platform_by_compact(platforms.PLATFORM_UNKNOWN_COMPACT)

AEL_compact_platform_Screenscraper_mapping = {
    '3do': 29,
    'cpc': 65,
    'a2600': 26,
    'a5200': 40,
    'a7800': 41,
    'atari-8bit': 43,
    'jaguar': 27,
    'jaguarcd': 171,
    'lynx': 28,
    'atari-st': 42,
    'wswan': 45,
    'wswancolor': 46,
    'loopy': 98,
    'pv1000': 74,
    'cvision': 48,
    'c16': 99,
    'c64': 66,
    'amiga': 64,
    'cd32': 130,
    'cdtv': 129,
    'vic20': 73,
    'arcadia2001': 94,
    'avision': 78,
    'scvision': 67,
    'channelf': 80,
    'fmtmarty': 97,
    'superacan': 100,
    'gp32': 101,
    'vectrex': 102,
    'gamemaster': 103,
    'lutro': 206,
    'tic80': 222,
    'odyssey2': 104,
    platforms.PLATFORM_MAME_COMPACT: 75,
    'ivision': 115,
    'msdos': 135,
    'msx': 113,
    'msx2': 116,
    'windows': 136,
    'xbox': 32,
    'xbox360': 33,
    'pce': 31,
    'pcecd': 114,
    'pcfx': 72,
    'sgx': 105,
    'n3ds': 17,
    'n64': 14,
    'n64dd': 122,
    'nds': 15,
    'ndsi': 15,
    'ereader': 119,
    'fds': 106,
    'gb': 9,
    'gba': 12,
    'gbcolor': 10,
    'gamecube': 13,
    'nes': 3,
    'pokemini': 211,
    'satellaview': 107,
    'snes': 4,
    'sufami': 108,
    'vb': 11,
    'wii': 16,
    'wiiu': 18,
    'g7400': 104,
    'scummvm': 123,
    '32x': 19,
    'dreamcast': 23,
    'gamegear': 21,
    'sms': 2,
    'megadrive': 1,
    'megacd': 20,
    'saturn': 22,
    'sg1000': 109,
    'x68k': 79,
    'spectrum': 76,
    'zx81': 77,
    'neocd': 70,
    'ngp': 25,
    'ngpcolor': 82,
    'psx': 57,
    'ps2': 58,
    'ps3': 59,
    'psp': 61,
    'psvita': 62,
    'tigergame': 121,
    'vsmile': 120,
    'supervision': 207
}

Screenscraper_AEL_compact_platform_mapping = {}
for key, value in AEL_compact_platform_Screenscraper_mapping.items():
    Screenscraper_AEL_compact_platform_mapping[value] = key        