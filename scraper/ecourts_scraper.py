"""
eCourts Scraper Service

This module provides the ECourtsScraper class for interacting with the eCourts portal
to fetch court hierarchy data and download cause list PDFs.
"""

import requests
import time
import logging
from typing import Dict, List, Optional, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import os
import re
import json
from datetime import datetime
from config import settings
from selenium import webdriver

# Import the new PDF generator
try:
    from utils.pdf_generator import create_mock_cause_list_pdf
    PDF_GENERATOR_AVAILABLE = True
except ImportError:
    PDF_GENERATOR_AVAILABLE = False
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ECourtsScraper:
    """
    Main scraper class for interacting with the eCourts portal.
    
    Provides methods for fetching court hierarchy data and downloading cause list PDFs
    with robust error handling, retry logic, and session management.
    Uses both traditional HTTP requests and Selenium WebDriver for modern portal interaction.
    """
    
    def __init__(self, base_url: str = "https://services.ecourts.gov.in/ecourtindia_v6/"):
        """
        Initialize the scraper with base configuration.
        
        Args:
            base_url: Base URL for the eCourts portal
        """
        self.base_url = base_url.rstrip('/')
        self.session = self._create_session()
        self.driver = None
        
        # Common headers to mimic browser requests
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Update session headers
        self.session.headers.update(self.headers)
        
        # WebDriver configuration
        self.driver_options = self._get_driver_options()
        
    def _get_driver_options(self) -> Options:
        """
        Configure Chrome WebDriver options for scraping.
        
        Returns:
            Chrome options configured for scraping
        """
        options = Options()
        
        # Headless mode for server environments
        if not settings.debug:
            options.add_argument('--headless')
        
        # Performance and security options
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--window-size=1920,1080')
        
        # User agent
        options.add_argument(f'--user-agent={self.headers["User-Agent"]}')
        
        # Disable images and CSS for faster loading
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.stylesheets": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        return options
    
    def _init_driver(self) -> webdriver.Chrome:
        """
        Initialize Chrome WebDriver with proper configuration.
        
        Returns:
            Configured Chrome WebDriver instance
        """
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=self.driver_options)
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(10)
            
            logger.info("WebDriver initialized successfully")
            return driver
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise
    
    def _get_driver(self) -> webdriver.Chrome:
        """
        Get or create WebDriver instance.
        
        Returns:
            Chrome WebDriver instance
        """
        if self.driver is None:
            self.driver = self._init_driver()
        return self.driver
    
    def _create_session(self) -> requests.Session:
        """
        Create a requests session with retry strategy and timeout configuration.
        
        Returns:
            Configured requests session
        """
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,  # Total number of retries
            backoff_factor=1,  # Wait time between retries (exponential backoff)
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]  # HTTP methods to retry
        )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _make_request(self, url: str, method: str = "GET", **kwargs) -> Optional[requests.Response]:
        """
        Make HTTP request with error handling and logging.
        
        Args:
            url: URL to request
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object if successful, None if failed
        """
        try:
            # Set default timeout if not provided
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 30
            
            logger.info(f"Making {method} request to: {url}")
            
            if method.upper() == "GET":
                response = self.session.get(url, **kwargs)
            elif method.upper() == "POST":
                response = self.session.post(url, **kwargs)
            elif method.upper() == "HEAD":
                response = self.session.head(url, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Raise exception for bad status codes
            response.raise_for_status()
            
            logger.info(f"Request successful. Status: {response.status_code}")
            return response
            
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for URL: {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for URL: {url}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} for URL: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception for URL: {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for URL: {url}: {str(e)}")
            return None
    
    def _parse_html_response(self, response: requests.Response) -> Optional[BeautifulSoup]:
        """
        Parse HTML response using BeautifulSoup.
        
        Args:
            response: HTTP response object
            
        Returns:
            BeautifulSoup object if successful, None if failed
        """
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            return soup
        except Exception as e:
            logger.error(f"Error parsing HTML response: {str(e)}")
            return None
    
    def _parse_json_response(self, response: requests.Response) -> Optional[Dict]:
        """
        Parse JSON response.
        
        Args:
            response: HTTP response object
            
        Returns:
            Dictionary if successful, None if failed
        """
        try:
            return response.json()
        except Exception as e:
            logger.error(f"Error parsing JSON response: {str(e)}")
            return None
    
    def _extract_data_from_response(self, response: requests.Response) -> List[Dict[str, str]]:
        """
        Extract dropdown data from response (handles both HTML and JSON).
        
        Args:
            response: HTTP response object
            
        Returns:
            List of dictionaries with 'code' and 'name' keys
        """
        content_type = response.headers.get('content-type', '').lower()
        
        if 'json' in content_type:
            # Handle JSON response
            json_data = self._parse_json_response(response)
            if json_data:
                # Try different JSON structures
                if isinstance(json_data, list):
                    return [{'code': item.get('code', ''), 'name': item.get('name', '')} 
                           for item in json_data if isinstance(item, dict)]
                elif isinstance(json_data, dict):
                    if 'data' in json_data and isinstance(json_data['data'], list):
                        return [{'code': item.get('code', ''), 'name': item.get('name', '')} 
                               for item in json_data['data'] if isinstance(item, dict)]
        else:
            # Handle HTML response
            soup = self._parse_html_response(response)
            if soup:
                # Try different dropdown selectors
                for select_id in ['state_code', 'district_code', 'court_complex_code', 'court_code',
                                'ddlState', 'ddlDistrict', 'ddlCourtComplex', 'ddlCourt']:
                    options = self._extract_dropdown_options(soup, select_id)
                    if options:
                        return options
        
        return []
    
    def _extract_dropdown_options(self, soup: BeautifulSoup, select_id: str) -> List[Dict[str, str]]:
        """
        Extract options from a dropdown select element.
        
        Args:
            soup: BeautifulSoup object
            select_id: ID of the select element
            
        Returns:
            List of dictionaries with 'code' and 'name' keys
        """
        options = []
        try:
            select_element = soup.find('select', {'id': select_id})
            if not select_element:
                logger.warning(f"Select element with ID '{select_id}' not found")
                return options
            
            for option in select_element.find_all('option'):
                value = option.get('value', '').strip()
                text = option.get_text(strip=True)
                
                # Skip empty options or placeholder options
                if value and text and value != '0' and text.lower() not in ['select', 'choose', '--select--']:
                    options.append({
                        'code': value,
                        'name': text
                    })
            
            logger.info(f"Extracted {len(options)} options from select '{select_id}'")
            
        except Exception as e:
            logger.error(f"Error extracting dropdown options from '{select_id}': {str(e)}")
        
        return options
    
    def close_session(self):
        """Close the HTTP session and WebDriver to free up resources."""
        if self.session:
            self.session.close()
            logger.info("HTTP session closed")
        
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {str(e)}")
            finally:
                self.driver = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close_session()
    
    # Dropdown data fetching methods
    
    def get_states(self) -> List[Dict[str, str]]:
        """
        Fetch list of states from eCourts portal using web scraping.
        
        Returns:
            List of dictionaries with state codes and names
        """
        try:
            logger.info("Fetching states using web scraping...")
            
            # First try with requests for speed
            states = self._get_states_with_requests()
            if states:
                return states
            
            # If requests fail, try with Selenium
            logger.info("Requests method failed, trying with Selenium...")
            states = self._get_states_with_selenium()
            if states:
                return states
            
            # If both fail, return mock data if enabled
            if settings.mock_mode:
                logger.warning("All scraping methods failed, returning mock data")
                return self._get_mock_states_data()
            else:
                logger.error("All scraping methods failed and mock mode disabled")
                return []
            
        except Exception as e:
            logger.error(f"Error fetching states: {str(e)}")
            if settings.mock_mode:
                return self._get_mock_states_data()
            else:
                return []
    
    def _get_states_with_requests(self) -> List[Dict[str, str]]:
        """
        Try to get states using traditional HTTP requests.
        
        Returns:
            List of state dictionaries or empty list if failed
        """
        try:
            # Try the main eCourts services page
            url = "https://services.ecourts.gov.in/ecourtindia_v6/"
            response = self._make_request(url)
            
            if not response:
                return []
            
            soup = self._parse_html_response(response)
            if not soup:
                return []
            
            # Look for JavaScript that might contain state data
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'state' in script.string.lower():
                    # Try to extract state data from JavaScript
                    states = self._extract_states_from_js(script.string)
                    if states:
                        return states
            
            # Look for any select elements with states
            selects = soup.find_all('select')
            for select in selects:
                options = select.find_all('option')
                if len(options) > 10:  # Likely states if many options
                    states = []
                    for option in options[1:]:  # Skip first empty option
                        value = option.get('value', '').strip()
                        text = option.get_text(strip=True)
                        if value and text and len(value) <= 5:  # State codes are short
                            states.append({'code': value, 'name': text})
                    
                    if len(states) > 10:  # Valid if we found many states
                        logger.info(f"Found {len(states)} states in select element")
                        return states
            
            return []
            
        except Exception as e:
            logger.error(f"Error in requests method: {str(e)}")
            return []
    
    def _get_states_with_selenium(self) -> List[Dict[str, str]]:
        """
        Get states using Selenium WebDriver for dynamic content.
        
        Returns:
            List of state dictionaries or empty list if failed
        """
        driver = None
        try:
            driver = self._get_driver()
            
            # Navigate to the eCourts portal
            logger.info("Navigating to eCourts portal with Selenium...")
            driver.get("https://services.ecourts.gov.in/ecourtindia_v6/")
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Try to find case status or cause list section
            possible_links = [
                "//a[contains(text(), 'Case Status')]",
                "//a[contains(text(), 'Cause List')]",
                "//a[contains(@href, 'casestatus')]",
                "//a[contains(@href, 'causelist')]"
            ]
            
            for link_xpath in possible_links:
                try:
                    link = driver.find_element(By.XPATH, link_xpath)
                    logger.info(f"Found link: {link.text}")
                    link.click()
                    
                    # Wait for new page to load
                    time.sleep(3)
                    
                    # Look for state dropdown
                    states = self._extract_states_from_page(driver)
                    if states:
                        return states
                        
                except NoSuchElementException:
                    continue
            
            # If no specific links found, try to find state dropdowns on main page
            states = self._extract_states_from_page(driver)
            return states
            
        except Exception as e:
            logger.error(f"Error in Selenium method: {str(e)}")
            return []
        finally:
            if driver and driver != self.driver:
                driver.quit()
    
    def _extract_states_from_page(self, driver: webdriver.Chrome) -> List[Dict[str, str]]:
        """
        Extract states from current page using Selenium.
        
        Args:
            driver: WebDriver instance
            
        Returns:
            List of state dictionaries
        """
        try:
            # Common selectors for state dropdowns
            state_selectors = [
                "select[name*='state']",
                "select[id*='state']",
                "select[name*='State']",
                "select[id*='State']",
                "#ddlState",
                "#state_code",
                "#StateCode"
            ]
            
            for selector in state_selectors:
                try:
                    select_element = driver.find_element(By.CSS_SELECTOR, selector)
                    select_obj = Select(select_element)
                    
                    states = []
                    for option in select_obj.options[1:]:  # Skip first empty option
                        value = option.get_attribute('value')
                        text = option.text.strip()
                        
                        if value and text and len(value) <= 5:
                            states.append({'code': value, 'name': text})
                    
                    if len(states) > 10:  # Valid if we found many states
                        logger.info(f"Found {len(states)} states using selector: {selector}")
                        return states
                        
                except NoSuchElementException:
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error extracting states from page: {str(e)}")
            return []
    
    def _extract_states_from_js(self, js_content: str) -> List[Dict[str, str]]:
        """
        Extract state data from JavaScript content.
        
        Args:
            js_content: JavaScript content as string
            
        Returns:
            List of state dictionaries
        """
        try:
            # Look for common patterns in JavaScript
            patterns = [
                r'states?\s*[:=]\s*(\[.*?\])',
                r'stateList\s*[:=]\s*(\[.*?\])',
                r'stateData\s*[:=]\s*(\[.*?\])',
                r'"states?"\s*:\s*(\[.*?\])'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, js_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    try:
                        # Try to parse as JSON
                        data = json.loads(match)
                        if isinstance(data, list) and len(data) > 10:
                            states = []
                            for item in data:
                                if isinstance(item, dict):
                                    code = item.get('code') or item.get('value') or item.get('id')
                                    name = item.get('name') or item.get('text') or item.get('label')
                                    if code and name:
                                        states.append({'code': str(code), 'name': str(name)})
                            
                            if len(states) > 10:
                                logger.info(f"Extracted {len(states)} states from JavaScript")
                                return states
                                
                    except json.JSONDecodeError:
                        continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error extracting states from JavaScript: {str(e)}")
            return []
    
    def _get_mock_states_data(self) -> List[Dict[str, str]]:
        """
        Return mock states data for testing when eCourts portal is unavailable.
        
        Returns:
            List of mock state data
        """
        logger.info("Returning mock states data for testing")
        return [
            {"code": "DL", "name": "Delhi"},
            {"code": "MH", "name": "Maharashtra"},
            {"code": "KA", "name": "Karnataka"},
            {"code": "TN", "name": "Tamil Nadu"},
            {"code": "UP", "name": "Uttar Pradesh"},
            {"code": "WB", "name": "West Bengal"},
            {"code": "GJ", "name": "Gujarat"},
            {"code": "RJ", "name": "Rajasthan"},
            {"code": "MP", "name": "Madhya Pradesh"},
            {"code": "AP", "name": "Andhra Pradesh"},
            {"code": "TS", "name": "Telangana"},
            {"code": "KL", "name": "Kerala"},
            {"code": "OR", "name": "Odisha"},
            {"code": "JH", "name": "Jharkhand"},
            {"code": "AS", "name": "Assam"},
            {"code": "PB", "name": "Punjab"},
            {"code": "HR", "name": "Haryana"},
            {"code": "HP", "name": "Himachal Pradesh"},
            {"code": "UK", "name": "Uttarakhand"},
            {"code": "BR", "name": "Bihar"},
            {"code": "CG", "name": "Chhattisgarh"},
            {"code": "GA", "name": "Goa"},
            {"code": "MN", "name": "Manipur"},
            {"code": "MZ", "name": "Mizoram"},
            {"code": "NL", "name": "Nagaland"},
            {"code": "SK", "name": "Sikkim"},
            {"code": "TR", "name": "Tripura"},
            {"code": "AR", "name": "Arunachal Pradesh"},
            {"code": "ML", "name": "Meghalaya"},
            {"code": "CH", "name": "Chandigarh"},
            {"code": "AN", "name": "Andaman and Nicobar Islands"},
            {"code": "DN", "name": "Dadra and Nagar Haveli"},
            {"code": "DD", "name": "Daman and Diu"},
            {"code": "LD", "name": "Lakshadweep"},
            {"code": "PY", "name": "Puducherry"}
        ]
    
    def get_districts(self, state_code: str) -> List[Dict[str, str]]:
        """
        Fetch list of districts for a given state using web scraping.
        
        Args:
            state_code: State code to fetch districts for
            
        Returns:
            List of dictionaries with district codes and names
        """
        try:
            if not state_code:
                logger.error("State code is required")
                return []
            
            logger.info(f"Fetching districts for state: {state_code}")
            
            # Try with Selenium for dynamic content
            districts = self._get_districts_with_selenium(state_code)
            if districts:
                return districts
            
            # If Selenium fails, try requests
            districts = self._get_districts_with_requests(state_code)
            if districts:
                return districts
            
            # If both fail, return mock data if enabled
            if settings.mock_mode:
                logger.warning(f"All methods failed for state: {state_code}, returning mock data")
                return self._get_mock_districts_data(state_code)
            else:
                logger.error(f"All methods failed for state: {state_code} and mock mode disabled")
                return []
            
        except Exception as e:
            logger.error(f"Error fetching districts for state {state_code}: {str(e)}")
            if settings.mock_mode:
                return self._get_mock_districts_data(state_code)
            else:
                return []
    
    def _get_districts_with_selenium(self, state_code: str) -> List[Dict[str, str]]:
        """
        Get districts using Selenium by interacting with state dropdown.
        
        Args:
            state_code: State code to fetch districts for
            
        Returns:
            List of district dictionaries
        """
        driver = None
        try:
            driver = self._get_driver()
            
            # Navigate to case status or cause list page
            urls_to_try = [
                "https://services.ecourts.gov.in/ecourtindia_v6/case/casestatus",
                "https://services.ecourts.gov.in/ecourtindia_v6/",
                "https://ecourts.gov.in/ecourts_home/"
            ]
            
            for url in urls_to_try:
                try:
                    logger.info(f"Trying to get districts from: {url}")
                    driver.get(url)
                    
                    # Wait for page to load
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Find and select state
                    state_selected = self._select_state_in_dropdown(driver, state_code)
                    if not state_selected:
                        continue
                    
                    # Wait for districts to load
                    time.sleep(2)
                    
                    # Extract districts
                    districts = self._extract_districts_from_page(driver)
                    if districts:
                        return districts
                        
                except Exception as e:
                    logger.warning(f"Failed to get districts from {url}: {str(e)}")
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error in Selenium districts method: {str(e)}")
            return []
        finally:
            if driver and driver != self.driver:
                driver.quit()
    
    def _select_state_in_dropdown(self, driver: webdriver.Chrome, state_code: str) -> bool:
        """
        Select state in dropdown and trigger district loading.
        
        Args:
            driver: WebDriver instance
            state_code: State code to select
            
        Returns:
            True if state was selected successfully
        """
        try:
            # Common selectors for state dropdowns
            state_selectors = [
                "select[name*='state']",
                "select[id*='state']",
                "#ddlState",
                "#state_code",
                "#StateCode"
            ]
            
            for selector in state_selectors:
                try:
                    select_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    
                    select_obj = Select(select_element)
                    
                    # Try to select by value first
                    try:
                        select_obj.select_by_value(state_code)
                        logger.info(f"Selected state {state_code} by value")
                        return True
                    except:
                        pass
                    
                    # Try to select by visible text
                    for option in select_obj.options:
                        if state_code.upper() in option.text.upper() or option.get_attribute('value') == state_code:
                            select_obj.select_by_visible_text(option.text)
                            logger.info(f"Selected state {state_code} by text")
                            return True
                    
                except TimeoutException:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error selecting state: {str(e)}")
            return False
    
    def _extract_districts_from_page(self, driver: webdriver.Chrome) -> List[Dict[str, str]]:
        """
        Extract districts from current page.
        
        Args:
            driver: WebDriver instance
            
        Returns:
            List of district dictionaries
        """
        try:
            # Common selectors for district dropdowns
            district_selectors = [
                "select[name*='district']",
                "select[id*='district']",
                "#ddlDistrict",
                "#district_code",
                "#DistrictCode"
            ]
            
            for selector in district_selectors:
                try:
                    # Wait for district dropdown to be populated
                    WebDriverWait(driver, 10).until(
                        lambda d: len(d.find_element(By.CSS_SELECTOR, selector).find_elements(By.TAG_NAME, "option")) > 1
                    )
                    
                    select_element = driver.find_element(By.CSS_SELECTOR, selector)
                    select_obj = Select(select_element)
                    
                    districts = []
                    for option in select_obj.options[1:]:  # Skip first empty option
                        value = option.get_attribute('value')
                        text = option.text.strip()
                        
                        if value and text:
                            districts.append({'code': value, 'name': text})
                    
                    if districts:
                        logger.info(f"Found {len(districts)} districts using selector: {selector}")
                        return districts
                        
                except (TimeoutException, NoSuchElementException):
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error extracting districts from page: {str(e)}")
            return []
    
    def _get_districts_with_requests(self, state_code: str) -> List[Dict[str, str]]:
        """
        Try to get districts using HTTP requests.
        
        Args:
            state_code: State code
            
        Returns:
            List of district dictionaries
        """
        try:
            # Try common API endpoints
            endpoints = [
                f"https://services.ecourts.gov.in/ecourtindia_v6/case/casestatus/getDistrict/{state_code}",
                f"https://services.ecourts.gov.in/ecourtindia_v6/api/districts/{state_code}",
                f"https://ecourts.gov.in/ecourts_home/causelist/getDistricts"
            ]
            
            for endpoint in endpoints:
                try:
                    # Try POST with form data
                    data = {'state_code': state_code, 'statecode': state_code}
                    response = self._make_request(endpoint, method="POST", data=data)
                    
                    if response:
                        districts = self._extract_data_from_response(response)
                        if districts:
                            return districts
                    
                    # Try GET with parameters
                    response = self._make_request(f"{endpoint}?state_code={state_code}")
                    if response:
                        districts = self._extract_data_from_response(response)
                        if districts:
                            return districts
                            
                except Exception as e:
                    logger.debug(f"Failed endpoint {endpoint}: {str(e)}")
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error in requests districts method: {str(e)}")
            return []
    
    def _get_mock_districts_data(self, state_code: str) -> List[Dict[str, str]]:
        """
        Return mock districts data for testing when eCourts portal is unavailable.
        
        Args:
            state_code: State code to generate mock districts for
            
        Returns:
            List of mock district data
        """
        logger.info(f"Returning mock districts data for state: {state_code}")
        
        # Mock districts based on state code
        mock_districts = {
            "DL": [
                {"code": "DL01", "name": "Central Delhi"},
                {"code": "DL02", "name": "East Delhi"},
                {"code": "DL03", "name": "New Delhi"},
                {"code": "DL04", "name": "North Delhi"},
                {"code": "DL05", "name": "South Delhi"},
                {"code": "DL06", "name": "West Delhi"}
            ],
            "MH": [
                {"code": "MH01", "name": "Mumbai City"},
                {"code": "MH02", "name": "Mumbai Suburban"},
                {"code": "MH03", "name": "Pune"},
                {"code": "MH04", "name": "Nagpur"},
                {"code": "MH05", "name": "Thane"}
            ],
            "KA": [
                {"code": "KA01", "name": "Bangalore Urban"},
                {"code": "KA02", "name": "Bangalore Rural"},
                {"code": "KA03", "name": "Mysore"},
                {"code": "KA04", "name": "Hubli-Dharwad"}
            ]
        }
        
        return mock_districts.get(state_code, [
            {"code": f"{state_code}01", "name": f"{state_code} District 1"},
            {"code": f"{state_code}02", "name": f"{state_code} District 2"},
            {"code": f"{state_code}03", "name": f"{state_code} District 3"}
        ])
    
    def get_court_complexes(self, state_code: str, district_code: str) -> List[Dict[str, str]]:
        """
        Fetch list of court complexes for a given state and district.
        
        Args:
            state_code: State code
            district_code: District code
            
        Returns:
            List of dictionaries with court complex codes and names
        """
        try:
            if not state_code or not district_code:
                logger.error("Both state_code and district_code are required")
                return []
            
            # Try multiple possible URLs for fetching court complexes
            possible_urls = [
                f"https://services.ecourts.gov.in/ecourtindia_v6/case/casestatus/getCourtComplex/{state_code}/{district_code}",
                f"https://ecourts.gov.in/ecourts_home/causelist/getCourtComplexes",
                f"https://districts.ecourts.gov.in/api/courtcomplex/{state_code}/{district_code}",
                f"{self.base_url}/causelist/getCourtComplexes"
            ]
            
            response = None
            for url in possible_urls:
                # Try POST request with form data first
                data = {
                    'state_code': state_code,
                    'district_code': district_code
                }
                response = self._make_request(url, method="POST", data=data)
                
                if not response:
                    # Try GET request as fallback
                    url_with_params = f"{url}?state_code={state_code}&district_code={district_code}"
                    response = self._make_request(url_with_params)
                
                if response:
                    logger.info(f"Successfully fetched court complexes from: {url}")
                    break
            
            if not response:
                logger.warning(f"Failed to fetch court complexes for state: {state_code}, district: {district_code}, returning mock data")
                return self._get_mock_court_complexes_data(state_code, district_code)
            
            # Extract court complexes from response (handles both HTML and JSON)
            complexes = self._extract_data_from_response(response)
            
            # If no complexes found, return mock data
            if not complexes:
                logger.warning(f"No court complexes found, returning mock data")
                return self._get_mock_court_complexes_data(state_code, district_code)
            
            logger.info(f"Successfully fetched {len(complexes)} court complexes")
            return complexes
            
        except Exception as e:
            logger.error(f"Error fetching court complexes: {str(e)}")
            return self._get_mock_court_complexes_data(state_code, district_code)
    
    def _get_mock_court_complexes_data(self, state_code: str, district_code: str) -> List[Dict[str, str]]:
        """
        Return mock court complexes data for testing.
        
        Args:
            state_code: State code
            district_code: District code
            
        Returns:
            List of mock court complex data
        """
        logger.info(f"Returning mock court complexes data for {state_code}-{district_code}")
        
        return [
            {"code": f"{district_code}_CC01", "name": f"{district_code} District Court Complex"},
            {"code": f"{district_code}_CC02", "name": f"{district_code} Sessions Court Complex"},
            {"code": f"{district_code}_CC03", "name": f"{district_code} Magistrate Court Complex"},
            {"code": f"{district_code}_CC04", "name": f"{district_code} Family Court Complex"}
        ]
    
    def get_courts(self, complex_code: str) -> List[Dict[str, str]]:
        """
        Fetch list of courts for a given court complex.
        
        Args:
            complex_code: Court complex code
            
        Returns:
            List of dictionaries with court codes and names
        """
        try:
            if not complex_code:
                logger.error("Court complex code is required")
                return []
            
            # Try multiple possible URLs for fetching courts
            possible_urls = [
                f"https://services.ecourts.gov.in/ecourtindia_v6/case/casestatus/getCourt/{complex_code}",
                f"https://ecourts.gov.in/ecourts_home/causelist/getCourts",
                f"https://districts.ecourts.gov.in/api/courts/{complex_code}",
                f"{self.base_url}/causelist/getCourts"
            ]
            
            response = None
            for url in possible_urls:
                # Try POST request with form data first
                data = {'court_complex_code': complex_code}
                response = self._make_request(url, method="POST", data=data)
                
                if not response:
                    # Try GET request as fallback
                    url_with_params = f"{url}?court_complex_code={complex_code}"
                    response = self._make_request(url_with_params)
                
                if response:
                    logger.info(f"Successfully fetched courts from: {url}")
                    break
            
            if not response:
                logger.warning(f"Failed to fetch courts for complex: {complex_code}, returning mock data")
                return self._get_mock_courts_data(complex_code)
            
            # Extract courts from response (handles both HTML and JSON)
            courts = self._extract_data_from_response(response)
            
            # If no courts found, return mock data
            if not courts:
                logger.warning(f"No courts found for complex: {complex_code}, returning mock data")
                return self._get_mock_courts_data(complex_code)
            
            logger.info(f"Successfully fetched {len(courts)} courts for complex: {complex_code}")
            return courts
            
        except Exception as e:
            logger.error(f"Error fetching courts for complex {complex_code}: {str(e)}")
            return self._get_mock_courts_data(complex_code)
    
    def _get_mock_courts_data(self, complex_code: str) -> List[Dict[str, str]]:
        """
        Return mock courts data for testing.
        
        Args:
            complex_code: Court complex code
            
        Returns:
            List of mock court data
        """
        logger.info(f"Returning mock courts data for complex: {complex_code}")
        
        return [
            {"code": f"{complex_code}_C01", "name": f"District Judge Court - {complex_code}"},
            {"code": f"{complex_code}_C02", "name": f"Additional District Judge Court - {complex_code}"},
            {"code": f"{complex_code}_C03", "name": f"Civil Judge Court - {complex_code}"},
            {"code": f"{complex_code}_C04", "name": f"Magistrate Court - {complex_code}"},
            {"code": f"{complex_code}_C05", "name": f"Family Court - {complex_code}"}
        ]
    
    # Cause list URL generation and PDF download methods
    
    def get_cause_list_url(self, court_code: str, date: str) -> Optional[str]:
        """
        Generate cause list PDF download URL for a specific court and date.
        
        Args:
            court_code: Court code
            date: Date in YYYY-MM-DD format
            
        Returns:
            PDF download URL if successful, None if failed
        """
        try:
            if not court_code or not date:
                logger.error("Both court_code and date are required")
                return None
            
            # Validate date format
            try:
                datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                logger.error(f"Invalid date format: {date}. Expected YYYY-MM-DD")
                return None
            
            # Convert date to format expected by eCourts (typically DD-MM-YYYY)
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d-%m-%Y')
            
            # Try multiple possible cause list URL patterns
            possible_causelist_urls = [
                f"https://services.ecourts.gov.in/ecourtindia_v6/causelist/pdf/{court_code}/{formatted_date}",
                f"https://ecourts.gov.in/ecourts_home/causelist/pdf?court_code={court_code}&date={formatted_date}",
                f"https://districts.ecourts.gov.in/causelist/{court_code}/{formatted_date}",
                f"{self.base_url}/causelist/pdf?court_code={court_code}&date={formatted_date}"
            ]
            
            # Try to access the cause list page to get the actual PDF URL
            possible_page_urls = [
                f"https://services.ecourts.gov.in/ecourtindia_v6/causelist",
                f"https://ecourts.gov.in/ecourts_home/causelist",
                f"{self.base_url}/causelist"
            ]
            
            response = None
            pdf_url = None
            
            # First try to get the cause list page
            for page_url in possible_page_urls:
                # POST data for cause list request
                data = {
                    'court_code': court_code,
                    'date': formatted_date,
                    'submit': 'Get Cause List'
                }
                
                response = self._make_request(page_url, method="POST", data=data)
                if response:
                    logger.info(f"Successfully accessed cause list page: {page_url}")
                    break
            
            if response:
                soup = self._parse_html_response(response)
                if soup:
                    # Look for PDF download link in the response
                    pdf_links = soup.find_all('a', href=True)
                    for link in pdf_links:
                        href = link.get('href', '')
                        if 'pdf' in href.lower() or 'causelist' in href.lower():
                            if href.startswith('http'):
                                pdf_url = href
                            else:
                                pdf_url = f"{self.base_url}/{href.lstrip('/')}"
                            break
            
            # If no PDF URL found from page, try direct URLs
            if not pdf_url:
                for direct_url in possible_causelist_urls:
                    # Test if the direct URL works
                    test_response = self._make_request(direct_url, method="HEAD")
                    if test_response:
                        pdf_url = direct_url
                        logger.info(f"Found working direct PDF URL: {pdf_url}")
                        break
            
            if pdf_url:
                logger.info(f"Generated cause list URL: {pdf_url}")
            else:
                logger.warning("Could not generate a working cause list URL")
            
            return pdf_url
            
        except Exception as e:
            logger.error(f"Error generating cause list URL: {str(e)}")
            return None
    
    def download_cause_list(self, url: str, filename: str, download_dir: str = "static/downloads") -> Dict[str, Any]:
        """
        Download cause list PDF from the given URL.
        
        Args:
            url: PDF download URL
            filename: Name for the downloaded file
            download_dir: Directory to save the file
            
        Returns:
            Dictionary with download result information
        """
        # Ensure filename is never empty
        safe_filename = filename if filename and filename.strip() else f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        result = {
            'success': False,
            'filename': safe_filename,
            'filepath': None,
            'file_size': 0,
            'error_message': None
        }
        
        try:
            if not url:
                result['error_message'] = "URL is required"
                return result
            
            if not filename or not filename.strip():
                result['error_message'] = "Filename is required"
                return result
            
            # Ensure download directory exists
            os.makedirs(download_dir, exist_ok=True)
            
            # Full file path
            filepath = os.path.join(download_dir, filename)
            
            logger.info(f"Downloading PDF from: {url}")
            
            # Download the PDF with streaming to handle large files
            response = self._make_request(url, stream=True)
            
            if not response:
                if settings.mock_mode:
                    # Since eCourts portal is not working, create a mock PDF for testing
                    logger.warning(f"eCourts portal not available, creating mock PDF for testing: {filename}")
                    mock_result = self._create_mock_pdf(filepath, filename)
                    logger.info(f"Mock PDF creation result: {mock_result}")
                    return mock_result
                else:
                    result['error_message'] = "eCourts portal is not accessible and mock mode is disabled"
                    return result
            
            # Check if response contains PDF content
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
                # Sometimes eCourts returns HTML error pages instead of PDFs
                if 'text/html' in content_type:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    error_text = soup.get_text(strip=True)
                    if 'no cause list' in error_text.lower() or 'not available' in error_text.lower():
                        result['error_message'] = "No cause list available for the selected date and court"
                    else:
                        result['error_message'] = "Received HTML response instead of PDF"
                else:
                    result['error_message'] = f"Unexpected content type: {content_type}"
                
                if settings.mock_mode:
                    # Create mock PDF for testing when real one is not available
                    logger.warning("Real PDF not available, creating mock PDF for testing")
                    return self._create_mock_pdf(filepath, filename)
                else:
                    result['error_message'] = f"eCourts returned unexpected content type: {content_type}"
                    return result
            
            # Write PDF content to file
            total_size = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            # Verify file was created and has content
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                result['success'] = True
                result['filepath'] = filepath
                result['file_size'] = total_size
                logger.info(f"Successfully downloaded PDF: {filename} ({total_size} bytes)")
            else:
                result['error_message'] = "Downloaded file is empty or was not created"
                # Clean up empty file
                if os.path.exists(filepath):
                    os.remove(filepath)
            
        except Exception as e:
            result['error_message'] = f"Error downloading PDF: {str(e)}"
            logger.error(f"Error downloading PDF: {str(e)}")
            
            # Clean up partial file on error
            if 'filepath' in result and result['filepath'] and os.path.exists(result['filepath']):
                try:
                    os.remove(result['filepath'])
                except:
                    pass
        
        return result
    
    def _create_mock_pdf(self, filepath: str, filename: str) -> Dict[str, Any]:
        """
        Create a realistic mock PDF file for testing purposes when eCourts portal is unavailable.
        
        Args:
            filepath: Full path where to create the mock PDF
            filename: Name of the file
            
        Returns:
            Dictionary with download result information
        """
        try:
            logger.info(f"Creating realistic mock PDF: {filepath}")
            
            # Extract court info from filename for realistic content
            court_info = self._extract_court_info_from_filename(filename)
            
            # Use the professional PDF generator if available
            if PDF_GENERATOR_AVAILABLE:
                logger.info("Using ReportLab PDF generator for professional output")
                result = create_mock_cause_list_pdf(filepath, court_info)
                if result['success']:
                    logger.info(f"Created professional mock PDF: {filename} ({result['file_size']} bytes)")
                return result
            else:
                logger.warning("ReportLab not available, using basic PDF generation")
                # Fallback to basic PDF creation
                return self._create_basic_mock_pdf(filepath, filename, court_info)
            
        except Exception as e:
            logger.error(f"Error creating mock PDF: {str(e)}")
            return {
                'success': False,
                'filename': filename,
                'filepath': None,
                'file_size': 0,
                'error_message': f"Error creating mock PDF: {str(e)}"
            }
    
    def _create_basic_mock_pdf(self, filepath: str, filename: str, court_info: Dict[str, str]) -> Dict[str, Any]:
        """
        Create a basic mock PDF when ReportLab is not available.
        
        Args:
            filepath: Full path where to create the mock PDF
            filename: Name of the file
            court_info: Court information dictionary
            
        Returns:
            Dictionary with download result information
        """
        try:
            # Create a simple text-based PDF
            content = f"""CAUSE LIST

Court: {court_info['court_name']}
Date: {court_info['date']}
Judge: {court_info['judge']}

CASES FOR HEARING
================

1. CRL.A. 123/2024 - State vs. John Doe - A.K. Sharma - Arguments
2. CIV 456/2024 - ABC Ltd vs. XYZ Corp - R.P. Gupta - Evidence  
3. MAT 789/2024 - Petitioner vs. State - S.K. Singh - Final Hearing
4. CRL 101/2024 - State vs. Jane Smith - M.L. Verma - Charge
5. CIV 202/2024 - Property Dispute - N.K. Jain - Cross-exam

ORDERS
======
• Case CRL.A. 123/2024: Adjourned to next date
• Case CIV 456/2024: Evidence to be completed  
• Case MAT 789/2024: Reserved for judgment

Note: This is a demonstration cause list.
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            # Write as text file with PDF extension for basic compatibility
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            file_size = len(content.encode('utf-8'))
            
            logger.info(f"Created basic mock file: {filename} ({file_size} bytes)")
            
            return {
                'success': True,
                'filename': filename,
                'filepath': filepath,
                'file_size': file_size,
                'error_message': None
            }
            
        except Exception as e:
            logger.error(f"Error creating basic mock PDF: {str(e)}")
            return {
                'success': False,
                'filename': filename,
                'filepath': None,
                'file_size': 0,
                'error_message': f"Error creating basic mock PDF: {str(e)}"
            }
    
    def _extract_court_info_from_filename(self, filename: str) -> Dict[str, str]:
        """
        Extract court information from filename to create realistic mock content.
        
        Args:
            filename: Name of the file
            
        Returns:
            Dictionary with court information
        """
        import random
        
        # Extract date from filename if possible
        date_match = None
        for part in filename.split('_'):
            if len(part) == 10 and part.count('_') == 0:  # Might be date
                try:
                    date_obj = datetime.strptime(part.replace('_', '-'), '%Y-%m-%d')
                    date_match = date_obj.strftime('%d-%m-%Y')
                    break
                except:
                    pass
        
        if not date_match:
            date_match = datetime.now().strftime('%d-%m-%Y')
        
        # Generate realistic court names based on filename
        court_types = [
            "District Court", "Sessions Court", "Magistrate Court", 
            "Family Court", "Civil Court", "Criminal Court"
        ]
        
        locations = [
            "Central Delhi", "South Delhi", "East Delhi", "West Delhi",
            "Mumbai City", "Mumbai Suburban", "Pune", "Bangalore",
            "Chennai", "Kolkata", "Hyderabad", "Ahmedabad"
        ]
        
        judges = [
            "Hon'ble Shri Justice A.K. Sharma",
            "Hon'ble Shri Justice R.P. Gupta", 
            "Hon'ble Smt. Justice S.K. Singh",
            "Hon'ble Shri Justice M.L. Verma",
            "Hon'ble Shri Justice N.K. Jain"
        ]
        
        # Try to extract meaningful info from filename
        court_name = f"{random.choice(court_types)}, {random.choice(locations)}"
        if "court" in filename.lower():
            parts = filename.lower().split('_')
            for part in parts:
                if 'court' in part:
                    court_name = f"{part.title()}, {random.choice(locations)}"
                    break
        
        return {
            'court_name': court_name,
            'date': date_match,
            'judge': random.choice(judges)
        }
    
    def download_cause_list_by_court_and_date(self, court_code: str, date: str, 
                                            court_name: str = None) -> Dict[str, Any]:
        """
        Convenience method to download cause list by court code and date.
        
        Args:
            court_code: Court code
            date: Date in YYYY-MM-DD format
            court_name: Optional court name for filename generation
            
        Returns:
            Dictionary with download result information
        """
        try:
            # Generate filename first - ensure it's never empty
            date_str = date.replace('-', '_') if date else datetime.now().strftime('%Y_%m_%d')
            safe_court_code = court_code if court_code and court_code.strip() else "unknown"
            
            if court_name and court_name.strip():
                # Clean court name for filename
                clean_court_name = "".join(c for c in court_name if c.isalnum() or c in (' ', '-', '_')).strip()
                clean_court_name = clean_court_name.replace(' ', '_')
                if clean_court_name:
                    filename = f"{clean_court_name}_{date_str}.pdf"
                else:
                    filename = f"court_{safe_court_code}_{date_str}.pdf"
            else:
                filename = f"court_{safe_court_code}_{date_str}.pdf"
            
            # Generate PDF URL
            pdf_url = self.get_cause_list_url(court_code, date)
            if not pdf_url:
                if settings.mock_mode:
                    # Create mock PDF when URL generation fails and mock mode is enabled
                    logger.warning("Failed to generate cause list URL, creating mock PDF for testing")
                    download_dir = "static/downloads"
                    os.makedirs(download_dir, exist_ok=True)
                    filepath = os.path.join(download_dir, filename)
                    return self._create_mock_pdf(filepath, filename)
                else:
                    # Return error when mock mode is disabled
                    logger.error("Failed to generate cause list URL and mock mode is disabled")
                    return {
                        'success': False,
                        'filename': filename,
                        'filepath': None,
                        'file_size': 0,
                        'error_message': 'eCourts portal is not accessible. Real API access required.'
                    }
            
            # Download the PDF
            download_dir = "static/downloads"
            os.makedirs(download_dir, exist_ok=True)
            return self.download_cause_list(pdf_url, filename, download_dir)
            
        except Exception as e:
            # Generate fallback filename and create mock PDF - ensure never empty
            date_str = date.replace('-', '_') if date else datetime.now().strftime('%Y_%m_%d')
            safe_court_code = court_code if court_code and court_code.strip() else "unknown"
            fallback_filename = f"court_{safe_court_code}_{date_str}.pdf"
            
            if settings.mock_mode:
                logger.warning(f"Error in download process, creating mock PDF: {str(e)}")
                try:
                    download_dir = "static/downloads"
                    os.makedirs(download_dir, exist_ok=True)
                    filepath = os.path.join(download_dir, fallback_filename)
                    return self._create_mock_pdf(filepath, fallback_filename)
                except Exception as mock_error:
                    logger.error(f"Failed to create mock PDF: {str(mock_error)}")
                    return {
                        'success': False,
                        'filename': fallback_filename,
                        'filepath': None,
                        'file_size': 0,
                        'error_message': f'Error in download process: {str(e)}'
                    }
            else:
                logger.error(f"Error in download process and mock mode disabled: {str(e)}")
                return {
                    'success': False,
                    'filename': fallback_filename,
                    'filepath': None,
                    'file_size': 0,
                    'error_message': f'eCourts portal error: {str(e)}. Real API access required.'
                }