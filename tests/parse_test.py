from re import sub
import unittest, os
import unittest.mock
from unittest.mock import MagicMock, patch

import logging

from resources.lib.scraper import ScreenScraper

logging.basicConfig(format = '%(asctime)s %(module)s %(levelname)s: %(message)s',
                datefmt = '%m/%d/%Y %I:%M:%S %p', level = logging.DEBUG)
logger = logging.getLogger(__name__)

def get_setting(key:str):
    if key == 'scraper_cache_dir':
         return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'output/'))
    return 'test'

def get_setting_int(key:str):
    return 0

class ParseTest(unittest.TestCase):
    
    @patch('resources.lib.scraper.settings.getSettingAsInt', autospec=True, side_effect=get_setting_int)
    @patch('resources.lib.scraper.settings.getSetting', autospec=True, side_effect=get_setting)
    def test_if_parsing_num_players_is_correct(self, setting_mock, setting_int_mock):
        # arrange
        target  = ScreenScraper()
        subject = { 'joueurs': { 'text': '1-4'}}
        expected = '4'

        # act
        actual = target._parse_meta_nplayers(subject)

        # assert
        assert actual == expected


if __name__ == '__main__':
   unittest.main()
