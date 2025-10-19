"""
Real eCourts Scraper Implementation

This module provides comprehensive web scraping for the eCourts portal
using both Selenium WebDriver and HTTP requests to extract real data.
"""

import time
import logging
import re
from typing import Dict, List, Optional, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class RealECourtsScraper:
    """
    Real eCourts scraper that can extract actual data from the portal.
    Uses Selenium WebDriver to handle dynamic content and JavaScript.
    """
    
    def __init__(self, headless: bool = True):
        """
        Initialize the real scraper.
        
        Args:
            headless: Whether to run browser in headless mode
        """
        self.headless = headless
        self.driver = None
        self.session = requests.Session()
        
        # Configure session headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
    
    def _init_driver(self) -> webdriver.Chrome:
        """Initialize Chrome WebDriver with better error handling."""
        try:
            options = Options()
            
            if self.headless:
                options.add_argument('--headless')
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Disable images for faster loading
            prefs = {"profile.managed_default_content_settings.images": 2}
            options.add_experimental_option("prefs", prefs)
            
            # Try to initialize WebDriver
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from selenium.webdriver.chrome.service import Service
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)
                
                logger.info("WebDriver initialized successfully")
                return driver
                
            except ImportError as e:
                logger.error(f"webdriver_manager not available: {str(e)}")
                # Try without webdriver_manager
                driver = webdriver.Chrome(options=options)
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)
                
                logger.info("WebDriver initialized without webdriver_manager")
                return driver
                
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise Exception(f"Cannot initialize Chrome WebDriver: {str(e)}. Please ensure Chrome is installed.")  
  def scrape_cause_list_direct(self, state_code, district_code, court_complex_code, 
                                court_code=None, date=None):
        """
        Directly scrape cause list from eCourts portal.
        
        Args:
            state_code: State code
            district_code: District code
            court_complex_code: Court complex code
            court_code: Specific court code (optional)
            date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary with scraped data or None if failed
        """
        try:
            logger.info(f"Starting direct cause list scraping for {state_code}-{district_code}-{court_complex_code}")
            
            # Initialize driver
            if not self.driver:
                self.driver = self._init_driver()
            
            # Navigate to eCourts cause list page
            causelist_urls = [
                "https://services.ecourts.gov.in/ecourtindia_v6/",
                "https://ecourts.gov.in/ecourts_home/",
                "https://districts.ecourts.gov.in/"
            ]
            
            for url in causelist_urls:
                try:
                    logger.info(f"Trying to access: {url}")
                    self.driver.get(url)
                    
                    # Wait for page load
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Look for cause list link
                    causelist_found = self._navigate_to_causelist_page()
                    if causelist_found:
                        break
                        
                except Exception as e:
                    logger.warning(f"Failed to access {url}: {str(e)}")
                    continue
            
            # Fill form and submit
            form_filled = self._fill_causelist_form(
                state_code, district_code, court_complex_code, court_code, date
            )
            
            if not form_filled:
                logger.error("Failed to fill cause list form")
                return None
            
            # Extract cause list data
            scraped_data = self._extract_causelist_data()
            
            if scraped_data:
                logger.info("Successfully scraped cause list data")
                return {
                    'success': True,
                    'data': scraped_data
                }
            else:
                logger.warning("No cause list data found")
                return None
                
        except Exception as e:
            logger.error(f"Error in direct scraping: {str(e)}")
            return None
    
    def _navigate_to_causelist_page(self):
        """Navigate to cause list page from main portal."""
        try:
            # Common cause list link texts and selectors
            causelist_selectors = [
                "//a[contains(text(), 'Cause List')]",
                "//a[contains(text(), 'Daily Cause List')]",
                "//a[contains(@href, 'causelist')]",
                "//a[contains(@href, 'cause-list')]",
                "#causelist",
                ".causelist-link"
            ]
            
            for selector in causelist_selectors:
                try:
                    if selector.startswith("//"):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    logger.info(f"Found cause list link: {element.text}")
                    element.click()
                    
                    # Wait for navigation
                    time.sleep(3)
                    return True
                    
                except NoSuchElementException:
                    continue
            
            # If no specific link found, check if we're already on a cause list page
            page_source = self.driver.page_source.lower()
            if 'cause list' in page_source or 'causelist' in page_source:
                logger.info("Already on cause list page")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error navigating to cause list page: {str(e)}")
            return False
    
    def _fill_causelist_form(self, state_code, district_code, court_complex_code, 
                           court_code, date):
        """Fill the cause list form with provided data."""
        try:
            logger.info("Filling cause list form...")
            
            # Convert date format if needed
            if date:
                try:
                    date_obj = datetime.strptime(date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d-%m-%Y')
                except:
                    formatted_date = date
            else:
                formatted_date = datetime.now().strftime('%d-%m-%Y')
            
            # Fill state dropdown
            state_filled = self._select_dropdown_option('state', state_code)
            if not state_filled:
                logger.error("Failed to select state")
                return False
            
            time.sleep(2)  # Wait for districts to load
            
            # Fill district dropdown
            district_filled = self._select_dropdown_option('district', district_code)
            if not district_filled:
                logger.error("Failed to select district")
                return False
            
            time.sleep(2)  # Wait for court complexes to load
            
            # Fill court complex dropdown
            complex_filled = self._select_dropdown_option('complex', court_complex_code)
            if not complex_filled:
                logger.error("Failed to select court complex")
                return False
            
            time.sleep(2)  # Wait for courts to load
            
            # Fill court dropdown if specific court provided
            if court_code and court_code != 'ALL':
                self._select_dropdown_option('court', court_code)
            
            # Fill date field
            date_filled = self._fill_date_field(formatted_date)
            if not date_filled:
                logger.warning("Could not fill date field, using default")
            
            # Submit form
            submit_clicked = self._click_submit_button()
            if not submit_clicked:
                logger.error("Failed to submit form")
                return False
            
            # Wait for results
            time.sleep(5)
            
            return True
            
        except Exception as e:
            logger.error(f"Error filling form: {str(e)}")
            return False
    
    def _select_dropdown_option(self, dropdown_type, value):
        """Select option in dropdown by type and value."""
        try:
            # Define selectors for different dropdown types
            selectors = {
                'state': [
                    "select[name*='state']", "select[id*='state']", 
                    "#ddlState", "#state_code"
                ],
                'district': [
                    "select[name*='district']", "select[id*='district']",
                    "#ddlDistrict", "#district_code"
                ],
                'complex': [
                    "select[name*='complex']", "select[id*='complex']",
                    "#ddlCourtComplex", "#court_complex_code"
                ],
                'court': [
                    "select[name*='court']", "select[id*='court']",
                    "#ddlCourt", "#court_code"
                ]
            }
            
            for selector in selectors.get(dropdown_type, []):
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    
                    select_obj = Select(element)
                    
                    # Try to select by value
                    try:
                        select_obj.select_by_value(value)
                        logger.info(f"Selected {dropdown_type} by value: {value}")
                        return True
                    except:
                        pass
                    
                    # Try to select by visible text containing the value
                    for option in select_obj.options:
                        if value.upper() in option.text.upper() or option.get_attribute('value') == value:
                            select_obj.select_by_visible_text(option.text)
                            logger.info(f"Selected {dropdown_type} by text: {option.text}")
                            return True
                    
                except TimeoutException:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error selecting {dropdown_type} dropdown: {str(e)}")
            return False
    
    def _fill_date_field(self, date_value):
        """Fill date input field."""
        try:
            date_selectors = [
                "input[name*='date']", "input[id*='date']",
                "#date", "#causelist_date", "#hearing_date"
            ]
            
            for selector in date_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    element.clear()
                    element.send_keys(date_value)
                    logger.info(f"Filled date field: {date_value}")
                    return True
                except NoSuchElementException:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error filling date field: {str(e)}")
            return False
    
    def _click_submit_button(self):
        """Click the submit/search button."""
        try:
            submit_selectors = [
                "input[type='submit']", "button[type='submit']",
                "//input[@value='Submit']", "//input[@value='Search']",
                "//button[contains(text(), 'Submit')]",
                "//button[contains(text(), 'Search')]",
                "//button[contains(text(), 'Get')]"
            ]
            
            for selector in submit_selectors:
                try:
                    if selector.startswith("//"):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    element.click()
                    logger.info("Clicked submit button")
                    return True
                    
                except NoSuchElementException:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error clicking submit button: {str(e)}")
            return False
    
    def _extract_causelist_data(self):
        """Extract cause list data from the results page."""
        try:
            logger.info("Extracting cause list data...")
            
            # Wait for results to load
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.page_source) > 1000  # Page has loaded content
            )
            
            # Look for cause list table or content
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract court information
            court_name = self._extract_court_name(soup)
            judge_name = self._extract_judge_name(soup)
            date_info = self._extract_date_info(soup)
            
            # Extract cases
            cases = self._extract_cases_from_table(soup)
            
            if not cases:
                # Try alternative extraction methods
                cases = self._extract_cases_from_text(soup)
            
            scraped_data = {
                'court_name': court_name,
                'judge': judge_name,
                'date': date_info,
                'cases': cases,
                'total_cases': len(cases)
            }
            
            logger.info(f"Extracted {len(cases)} cases from cause list")
            return scraped_data
            
        except Exception as e:
            logger.error(f"Error extracting cause list data: {str(e)}")
            return None
    
    def _extract_court_name(self, soup):
        """Extract court name from page."""
        try:
            # Look for court name in common locations
            selectors = [
                'h1', 'h2', 'h3', '.court-name', '#court-name',
                '.header', '.title'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    if 'court' in text.lower() and len(text) < 200:
                        return text
            
            return "Court Name Not Found"
            
        except:
            return "Court Name Not Found"
    
    def _extract_judge_name(self, soup):
        """Extract judge name from page."""
        try:
            # Look for judge name patterns
            text = soup.get_text()
            
            judge_patterns = [
                r"Hon'ble\s+.*?Justice\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r"Judge\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r"Presiding\s+Officer\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
            ]
            
            for pattern in judge_patterns:
                match = re.search(pattern, text)
                if match:
                    return f"Hon'ble {match.group(1)}"
            
            return "Hon'ble Court"
            
        except:
            return "Hon'ble Court"
    
    def _extract_date_info(self, soup):
        """Extract date information from page."""
        try:
            text = soup.get_text()
            
            # Look for date patterns
            date_patterns = [
                r"Date\s*:\s*(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
                r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
            
            return datetime.now().strftime('%d-%m-%Y')
            
        except:
            return datetime.now().strftime('%d-%m-%Y')
    
    def _extract_cases_from_table(self, soup):
        """Extract cases from HTML table."""
        try:
            cases = []
            
            # Look for tables containing case data
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                
                # Skip header row
                for row in rows[1:]:
                    cells = row.find_all(['td', 'th'])
                    
                    if len(cells) >= 3:  # Minimum columns for case data
                        case_data = {
                            'case_number': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                            'parties': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                            'advocate': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                            'stage': cells[3].get_text(strip=True) if len(cells) > 3 else 'For Hearing'
                        }
                        
                        # Only add if case number exists
                        if case_data['case_number']:
                            cases.append(case_data)
            
            return cases
            
        except Exception as e:
            logger.error(f"Error extracting cases from table: {str(e)}")
            return []
    
    def _extract_cases_from_text(self, soup):
        """Extract cases from plain text when no table structure."""
        try:
            cases = []
            text = soup.get_text()
            
            # Look for case number patterns
            case_patterns = [
                r"(\w+\.?\s*\d+/\d+)\s*[-–]\s*([^-–\n]+?)(?:\s*[-–]\s*([^-–\n]+?))?(?:\s*[-–]\s*([^-–\n]+?))?",
                r"(\d+/\d+)\s*([^0-9\n]+?)(?:\n|$)"
            ]
            
            for pattern in case_patterns:
                matches = re.findall(pattern, text, re.MULTILINE)
                
                for match in matches:
                    if len(match) >= 2:
                        case_data = {
                            'case_number': match[0].strip(),
                            'parties': match[1].strip() if len(match) > 1 else '',
                            'advocate': match[2].strip() if len(match) > 2 else '',
                            'stage': match[3].strip() if len(match) > 3 else 'For Hearing'
                        }
                        
                        cases.append(case_data)
            
            # If no cases found, create a sample case
            if not cases:
                cases.append({
                    'case_number': 'No cases found',
                    'parties': 'No cause list available for selected date',
                    'advocate': '',
                    'stage': ''
                })
            
            return cases[:20]  # Limit to 20 cases
            
        except Exception as e:
            logger.error(f"Error extracting cases from text: {str(e)}")
            return []
    
    def close(self):
        """Close the scraper and clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("WebDriver closed")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {str(e)}")
            finally:
                self.driver = None
        
        if self.session:
            self.session.close()
            logger.info("Session closed")