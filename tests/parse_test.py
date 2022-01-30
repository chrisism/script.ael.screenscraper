import unittest, os
import unittest.mock
from unittest.mock import patch

import logging

from tests.fakes import FakeFile
from resources.lib.scraper import ScreenScraper

logging.basicConfig(format = '%(asctime)s %(module)s %(levelname)s: %(message)s',
                datefmt = '%m/%d/%Y %I:%M:%S %p', level = logging.DEBUG)
logger = logging.getLogger(__name__)

def get_setting_int(key:str):
    return 0

class ParseTest(unittest.TestCase):

    @patch('akl.scrapers.kodi.getAddonDir', autospec=True, return_value=FakeFile("/test"))
    @patch('akl.scrapers.settings.getSettingAsFilePath', autospec=True, return_value=FakeFile("/test"))    
    @patch('resources.lib.scraper.settings.getSettingAsInt', autospec=True, side_effect=get_setting_int)
    def test_if_parsing_num_players_is_correct(self, setting_int_mock, cachedir_mock, addondir_mock):
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
