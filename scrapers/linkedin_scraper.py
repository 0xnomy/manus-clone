import asyncio
import platform
import json
import os
from datetime import datetime
from typing import Dict, List, Any
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set Windows event loop policy
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

class LinkedInScraper:
    """
    Wrapper class for LinkedInProfileScraper that implements async context manager
    and maintains compatibility with the existing task executor system.
    """
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.profile_scraper = LinkedInProfileScraper(headless=headless, timeout=timeout)
        self.browser = None
        self.context = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.browser:
            await self.browser.close()
    
    async def scrape_profile(self, url: str) -> Dict:
        """
        Scrape LinkedIn profile and return data in the format expected by the task executor.
        
        Args:
            url: LinkedIn profile URL
            
        Returns:
            Dict: Profile data with fields compatible with ScrapedData model
        """
        try:
            # Use the profile scraper to get raw data
            raw_data = await self.profile_scraper.scrape_profile(url)
            
            if not raw_data or 'error' in raw_data:
                return None
            
            # Transform the data to match expected format
            transformed_data = {
                'name': raw_data.get('name', 'Unknown'),
                'headline': raw_data.get('headline', ''),
                'location': raw_data.get('location', ''),
                'summary': raw_data.get('about', ''),  # Map 'about' to 'summary'
                'experience': raw_data.get('experience', []),
                'skills': self._extract_skills_from_data(raw_data),  # Extract skills from various sources
                'education': raw_data.get('education', []),
                'contact_info': {},  # Placeholder - not extracted by current scraper
                'scraped_at': raw_data.get('scraped_at', datetime.now().isoformat()),
                'source': 'LinkedIn',
                'profile_url': raw_data.get('source_url', url),
                'activity_posts': raw_data.get('activity_posts', [])
            }
            
            return transformed_data
            
        except Exception as e:
            print(f"❌ Error in LinkedInScraper.scrape_profile: {e}")
            return None
    
    def _extract_skills_from_data(self, raw_data: Dict) -> List[str]:
        """
        Extract skills from various data sources in the profile.
        
        Args:
            raw_data: Raw profile data from LinkedInProfileScraper
            
        Returns:
            List[str]: Extracted skills
        """
        skills = set()
        
        # Extract from headline
        headline = raw_data.get('headline', '')
        if headline:
            skills.update(self._extract_skills_from_text(headline))
        
        # Extract from about section
        about = raw_data.get('about', '')
        if about:
            skills.update(self._extract_skills_from_text(about))
        
        # Extract from experience
        experience = raw_data.get('experience', [])
        for exp in experience:
            title = exp.get('title', '')
            if title:
                skills.update(self._extract_skills_from_text(title))
        
        return list(skills)
    
    def _extract_skills_from_text(self, text: str) -> set:
        """
        Extract common skills from text.
        
        Args:
            text: Text to extract skills from
            
        Returns:
            set: Set of found skills
        """
        common_skills = [
            'python', 'javascript', 'java', 'react', 'node.js', 'sql', 'aws',
            'machine learning', 'ai', 'data analysis', 'project management',
            'agile', 'scrum', 'marketing', 'sales', 'design', 'ui/ux',
            'html', 'css', 'typescript', 'angular', 'vue', 'docker', 'kubernetes',
            'git', 'github', 'jenkins', 'jira', 'confluence', 'slack', 'zoom',
            'excel', 'powerpoint', 'word', 'photoshop', 'illustrator', 'figma',
            'tableau', 'power bi', 'r', 'matlab', 'tensorflow', 'pytorch',
            'scikit-learn', 'pandas', 'numpy', 'matplotlib', 'seaborn'
        ]
        
        found_skills = set()
        text_lower = text.lower()
        
        for skill in common_skills:
            if skill.lower() in text_lower:
                found_skills.add(skill)
        
        return found_skills

class LinkedInProfileScraper:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.email = os.getenv('LINKEDIN_EMAIL')
        self.password = os.getenv('LINKEDIN_PASSWORD')
        
        if not self.email or not self.password:
            raise ValueError("LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env file")
    
    async def login_to_linkedin(self, page) -> bool:
        """Login to LinkedIn using credentials from .env file."""
        try:
            print(f"🔐 Logging in with: {self.email}")
            
            await page.goto("https://www.linkedin.com/login", wait_until='domcontentloaded', timeout=self.timeout)
            await page.wait_for_timeout(2000)
            
            await page.fill('#username', self.email)
            await page.fill('#password', self.password)
            await page.click('button[type="submit"]')
            
            await page.wait_for_timeout(5000)
            
            current_url = page.url
            if "feed" in current_url or "mynetwork" in current_url:
                print("✅ Login successful!")
                return True
            else:
                print("❌ Login failed - check credentials")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    async def scrape_profile(self, url: str) -> Dict:
        """Scrape comprehensive LinkedIn profile data."""
        if "linkedin.com/in/" not in url or "/company/" in url:
            return {"error": "Not a valid LinkedIn profile URL"}
        
        try:
            print(f"🔗 Scraping LinkedIn profile: {url}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding'
                    ]
                )
                
                try:
                    context = await browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = await context.new_page()
                    
                    if not await self.login_to_linkedin(page):
                        return {"error": "Failed to login to LinkedIn"}
                    
                    await page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
                    await page.wait_for_timeout(3000)
                    
                    profile_root = self._get_profile_root(page.url or url)
                    
                    profile_data = await self.extract_profile_data(page, profile_root)
                    profile_data['source_url'] = url
                    profile_data['scraped_at'] = datetime.now().isoformat()
                    
                    return profile_data
                    
                finally:
                    await browser.close()
                    
        except Exception as e:
            print(f"❌ Error scraping profile {url}: {e}")
            return {
                'error': f'Scraping failed: {str(e)}',
                'source_url': url
            }
    
    def _get_profile_root(self, url: str) -> str:
        """Normalize a profile URL to canonical root 'https://www.linkedin.com/in/<handle>/'"""
        try:
            parsed = urlparse(url.split('?')[0].split('#')[0])
            parts = [p for p in parsed.path.split('/') if p]
            if 'in' in parts:
                idx = parts.index('in')
                handle = parts[idx + 1] if len(parts) > idx + 1 else ''
                root = f"{parsed.scheme}://{parsed.netloc}/in/{handle}/"
                return root
        except Exception:
            pass
        # Fallback: ensure trailing slash
        return url if url.endswith('/') else url + '/'

    async def _progressive_scroll(self, page, steps: int = 6, delay_ms: int = 600) -> None:
        try:
            for i in range(steps):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight/3)")
                await page.wait_for_timeout(delay_ms)
        except Exception:
            pass

    async def _open_detail(self, page, profile_root: str, anchor_suffix: str, expect_selector: str) -> bool:
        """Try to open details via anchor click; fallback to direct URL. Wait for selector and scroll."""
        try:
            # Try anchor click from main profile
            try:
                await page.goto(profile_root, wait_until='domcontentloaded', timeout=self.timeout)
                await page.wait_for_timeout(1200)
                await self._progressive_scroll(page, steps=4)
                anchor = await page.query_selector(f'a[href$="/{anchor_suffix}"]')
                if anchor:
                    await anchor.click(force=True)
                    await page.wait_for_timeout(1800)
            except Exception:
                pass

            # Ensure we're on the detail URL
            target_url = profile_root + anchor_suffix
            if not page.url.rstrip('/').endswith(anchor_suffix.rstrip('/')):
                await page.goto(target_url, wait_until='domcontentloaded', timeout=self.timeout)
            await page.wait_for_timeout(2000)
            try:
                await page.wait_for_selector(expect_selector, timeout=8000)
            except Exception:
                # still try to scroll to trigger lazy content
                pass
            await self._progressive_scroll(page, steps=6)
            return True
        except Exception:
            return False

    async def extract_profile_data(self, page, profile_root: str) -> Dict:
        """Extract all profile data from the page."""
        profile_data = {}
        
        try:
            # Basic profile information
            profile_data.update(await self.extract_basic_info(page))
            
            # About section
            profile_data['about'] = await self.extract_about_section(page)
            
            # Experience
            profile_data['experience'] = await self.extract_experience(page, profile_root)
            
            # Education
            profile_data['education'] = await self.extract_education(page, profile_root)
            
            # Activity posts
            profile_data['activity_posts'] = await self.extract_activity_posts(page, profile_root)
            
        except Exception as e:
            print(f"⚠️ Error extracting profile data: {e}")
            profile_data['error'] = str(e)
        
        return profile_data
    
    async def extract_basic_info(self, page) -> Dict:
        """Extract basic profile information."""
        basic_info = {}
        
        try:
            # Name - Most reliable selectors
            name_selectors = [
                'h1.text-heading-xlarge',
                '.text-heading-xlarge',
                'h1',
                '.pv-text-details__left-panel h1'
            ]
            
            for selector in name_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        name = (await element.text_content()).strip()
                        if name and len(name) > 1:
                            basic_info['name'] = name
                            print(f"✅ Found name: {name}")
                            break
                except:
                    continue
            
            # Headline
            headline_selectors = [
                '.text-body-medium.break-words',
                '.pv-text-details__left-panel .text-body-medium',
                '.pv-text-details__left-panel .text-body-medium.break-words'
            ]
            
            for selector in headline_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        headline = (await element.text_content()).strip()
                        if headline and len(headline) > 5:
                            basic_info['headline'] = headline
                            print(f"✅ Found headline: {headline}")
                            break
                except:
                    continue
            
            # Location
            location_selectors = [
                '.text-body-small.inline.t-black--light.break-words',
                '.pv-text-details__left-panel .text-body-small',
                '.pv-text-details__left-panel .text-body-small.inline.t-black--light.break-words'
            ]
            
            for selector in location_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        location = (await element.text_content()).strip()
                        if location and len(location) > 2:
                            basic_info['location'] = location
                            print(f"✅ Found location: {location}")
                            break
                except:
                    continue
            
            # Profile image
            img_selectors = [
                '.pv-top-card-profile-picture__image',
                '.profile-picture img',
                'img[alt*="profile"]',
                '.pv-top-card__photo img'
            ]
            
            for selector in img_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        src = await element.get_attribute('src')
                        if src and src.startswith('http'):
                            basic_info['profile_image'] = src
                            print("✅ Found profile image")
                            break
                except:
                    continue
                    
        except Exception as e:
            print(f"⚠️ Error extracting basic info: {e}")
        
        return basic_info
    
    async def extract_about_section(self, page) -> str:
        """Extract about section content."""
        try:
            # Scroll to load content
            await page.evaluate("window.scrollTo(0, 500)")
            await page.wait_for_timeout(2000)
            
            # Multiple about section selectors to try
            about_section_selectors = [
                # Your exact selector
                '#profile-content > div > div.scaffold-layout.scaffold-layout--breakpoint-none.scaffold-layout--main-aside.scaffold-layout--single-column.scaffold-layout--reflow.pv-profile.pvs-loader-wrapper__shimmer--animate > div > div > main > section:nth-child(2) > div.display-flex.ph5.pv3 > div',
                # Alternative about section selectors
                'section[data-section="about"]',
                '[data-view-name="profile-about"]',
                'section:has([data-field="about"])',
                'section.artdeco-card:nth-child(2)',
                '#profile-content main section:nth-child(2)',
                '.pv-about-section',
                '.about-section'
            ]
            
            # Try each selector
            for selector in about_section_selectors:
                try:
                    about_element = await page.query_selector(selector)
                    if about_element:
                        # Look for text content within the about section
                        text_selectors = [
                            '.inline-show-more-text__text',
                            '.pv-shared-text-with-see-more',
                            '.pv-about__summary-text',
                            'span[aria-hidden="true"]',
                            'div > span',
                            'p'
                        ]
                        
                        for text_sel in text_selectors:
                            text_elem = await about_element.query_selector(text_sel)
                            if text_elem:
                                text = (await text_elem.text_content()).strip()
                                if text and len(text) > 20 and 'about' not in text.lower()[:10]:
                                    print(f"✅ Found about section: {len(text)} characters")
                                    return text
                        
                        # If no specific text element found, try the whole section
                        text = (await about_element.text_content()).strip()
                        if text and len(text) > 20 and len(text) < 2000:
                            # Filter out common non-about content
                            if not any(term in text.lower() for term in ['experience', 'education', 'skills', 'activity', 'see more', 'show all']):
                                print(f"✅ Found about section: {len(text)} characters")
                                return text
                except:
                    continue
            
            # Fallback selectors
            about_selectors = [
                '[data-generated-suggestion-target] .inline-show-more-text__text',
                '.pv-shared-text-with-see-more .inline-show-more-text__text',
                '.pv-about__summary-text .inline-show-more-text__text',
                '[data-view-name="profile-about"] .inline-show-more-text__text',
                '.pv-about-section .inline-show-more-text__text',
                'section[data-section="about"] .inline-show-more-text__text',
                '.about-section .inline-show-more-text__text',
                '.pv-shared-text-with-see-more',
                '.inline-show-more-text',
                '[data-view-name="profile-about"] span[aria-hidden="true"]',
                '.pv-about__summary-text',
                '.pv-about__summary-text .inline-show-more-text'
            ]
            
            for selector in about_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        text = (await element.text_content()).strip()
                        if text and len(text) > 20:
                            print(f"✅ Found about section: {len(text)} characters")
                            return text
                except:
                    continue
            
            print("⚠️ No about section found")
            return ""
            
        except Exception as e:
            print(f"⚠️ Error extracting about section: {e}")
            return ""
    
    async def extract_experience(self, page, profile_root: str) -> List[Dict]:
        """Extract work experience using exact LinkedIn selectors."""
        experience = []
        
        try:
            # 1) Try user's exact experience section path on the main profile
            try:
                exact_exp_section = '#profile-content > div > div.scaffold-layout.scaffold-layout--breakpoint-none.scaffold-layout--main-aside.scaffold-layout--single-column.scaffold-layout--reflow.pv-profile.pvs-loader-wrapper__shimmer--animate > div > div > main > section:nth-child(3) > div.jEmyvosBamZBqtuVXgQXYBaKSHXgyPFHMUShdfc'
                section_el = await page.query_selector(exact_exp_section)
                if section_el:
                    exp_items_exact = await section_el.query_selector_all('ul > li')
                    for item in exp_items_exact[:5]:
                        try:
                            exp_data: Dict[str, Any] = {}
                            # Prefer the inner content container when present
                            content = await item.query_selector('div > div.display-flex.flex-column.align-self-center.flex-grow-1')
                            target = content or item
                            # Title
                            title_elem = await target.query_selector('.t-bold span[aria-hidden="true"], h3, .t-bold')
                            if title_elem:
                                t = (await title_elem.text_content()).strip()
                                if t:
                                    exp_data['title'] = t
                            # Company
                            company_elem = await target.query_selector('.t-normal span[aria-hidden="true"], h4, .t-normal')
                            if company_elem:
                                c = (await company_elem.text_content()).strip()
                                if c:
                                    exp_data['company'] = c
                            # Duration
                            duration_elem = await target.query_selector('.t-black--light span[aria-hidden="true"], .t-black--light')
                            if duration_elem:
                                d = (await duration_elem.text_content()).strip()
                                if d:
                                    exp_data['duration'] = d
                            # Add if looks valid
                            if exp_data.get('title') and exp_data.get('company'):
                                experience.append(exp_data)
                        except Exception:
                            continue
                    if experience:
                        print(f"✅ Extracted {len(experience)} experience entries (exact selectors)")
                        return experience
            except Exception:
                pass

            # Navigate explicitly to the experience details page for reliability
            await self._open_detail(
                page,
                profile_root,
                'details/experience/',
                'ul.pvs-list__paged-list-items'
            )
            
            exp_items = await page.query_selector_all('ul.pvs-list__paged-list-items > li, li.pvs-list__item--line-separated, .pvs-entity')
            
            print(f"✅ Found {len(exp_items)} experience items")
            
            for item in exp_items[:5]:  # Limit to 5 items
                try:
                    exp_data = {}
                    
                    # Job title - multiple selector options
                    title_selectors = [
                        '.t-bold span[aria-hidden="true"]',
                        '.pvs-entity__caption-wrapper .t-bold span',
                        '[data-field="experience_company_logo"] + div .t-bold span',
                        '.pv-entity__summary-info .t-bold span',
                        '.experience-item__title span',
                        '.t-16 .t-bold span[aria-hidden="true"]'
                    ]
                    
                    for title_sel in title_selectors:
                        title_elem = await item.query_selector(title_sel)
                        if title_elem:
                            title = (await title_elem.text_content()).strip()
                            if title and len(title) > 2 and not any(edu_word in title.lower() for edu_word in ['university', 'college', 'bachelor', 'master', 'phd', 'degree']):
                                exp_data['title'] = title
                                break
                    
                    # Company - multiple selector options
                    company_selectors = [
                        '.t-normal span[aria-hidden="true"]',
                        '.pvs-entity__caption-wrapper .t-normal span',
                        '.pv-entity__secondary-title span',
                        '.experience-item__company span',
                        '.t-14 .t-normal span[aria-hidden="true"]'
                    ]
                    
                    for company_sel in company_selectors:
                        company_elem = await item.query_selector(company_sel)
                        if company_elem:
                            company = (await company_elem.text_content()).strip()
                            if company and len(company) > 2 and not any(edu_word in company.lower() for edu_word in ['university', 'college', 'bachelor', 'master', 'phd', 'degree']):
                                exp_data['company'] = company
                                break
                    
                    # Duration - multiple selector options
                    duration_selectors = [
                        '.t-black--light span[aria-hidden="true"]',
                        '.pvs-entity__caption-wrapper .t-black--light span',
                        '.pv-entity__dates span',
                        '.experience-item__duration span',
                        '.t-12 .t-black--light span[aria-hidden="true"]'
                    ]
                    
                    for duration_sel in duration_selectors:
                        duration_elem = await item.query_selector(duration_sel)
                        if duration_elem:
                            duration = (await duration_elem.text_content()).strip()
                            if duration and len(duration) > 2:
                                exp_data['duration'] = duration
                                break

                    # Handle grouped roles under one company (nested list)
                    if not exp_data.get('title'):
                        nested_roles = await item.query_selector_all('.pvs-entity__sub-components li')
                        for role in nested_roles[:3]:
                            role_title = await role.query_selector('.t-bold span[aria-hidden="true"]')
                            role_company = await role.query_selector('.t-normal span[aria-hidden="true"]')
                            role_duration = await role.query_selector('.t-black--light span[aria-hidden="true"]')
                            rtitle = (await role_title.text_content()).strip() if role_title else None
                            rcomp = (await role_company.text_content()).strip() if role_company else None
                            rdur = (await role_duration.text_content()).strip() if role_duration else None
                            if rtitle and rcomp:
                                experience.append({
                                    'title': rtitle,
                                    'company': rcomp,
                                    **({'duration': rdur} if rdur else {})
                                })
                        # Skip adding the parent if nested roles were extracted
                        if experience:
                            continue
                    
                    # Relaxed acceptance: include if at least title OR company is present
                    if exp_data and (('title' in exp_data) or ('company' in exp_data)):
                        title_val = exp_data.get('title', '')
                        company_val = exp_data.get('company', '')
                        title_lower = title_val.lower()
                        company_lower = company_val.lower()

                        # Exclude obvious non-experience content/UI
                        exclude_keywords = [
                            'top skills', 'skills', 'skill', 'endorsement', 'endorsed', 'show more',
                            'see all', 'view more', 'expand', 'collapse', 'programming language',
                            'activity', 'posts', 'likes', 'comments', 'shares', 'reactions',
                            'connections', 'followers', 'following', 'about'
                        ]
                        is_excluded = any(keyword in title_lower or keyword in company_lower for keyword in exclude_keywords)

                        # Basic sanity checks
                        if title_val.startswith('•') or company_val.startswith('•'):
                            is_excluded = True
                        if title_val and company_val and title_val == company_val:
                            is_excluded = True

                        # Length guards (relaxed)
                        title_ok = (not title_val) or (len(title_val) >= 2)
                        company_ok = (not company_val) or (len(company_val) >= 2)

                        if (not is_excluded) and title_ok and company_ok:
                            experience.append(exp_data)
                            
                except Exception as e:
                    print(f"⚠️ Error extracting experience item: {e}")
                    continue
            
            print(f"✅ Extracted {len(experience)} experience entries")
            
        except Exception as e:
            print(f"⚠️ Error extracting experience: {e}")
        
        return experience
    
    async def extract_education(self, page, profile_root: str) -> List[Dict]:
        """Extract education information using exact LinkedIn selectors."""
        education = []
        
        try:
            # 1) Try user's exact education paths on the main profile first
            try:
                base_path = '#profile-content > div > div.scaffold-layout.scaffold-layout--breakpoint-none.scaffold-layout--main-aside.scaffold-layout--single-column.scaffold-layout--reflow.pv-profile.pvs-loader-wrapper__shimmer--animate > div > div > main > section:nth-child(5) > div.jEmyvosBamZBqtuVXgQXYBaKSHXgyPFHMUShdfc > ul'
                exact_selectors = [
                    base_path + ' > li:nth-child(1) > div > div.display-flex.flex-column.align-self-center.flex-grow-1',
                    base_path + ' > li:nth-child(2) > div > div.display-flex.flex-column.align-self-center.flex-grow-1',
                ]
                exact_items = []
                for sel in exact_selectors:
                    el = await page.query_selector(sel)
                    if el:
                        exact_items.append(el)
                # If not found specific nth-childs, fall back to all list items in section
                if not exact_items:
                    section_el = await page.query_selector(base_path)
                    if section_el:
                        exact_items = await section_el.query_selector_all('> li > div > div.display-flex.flex-column.align-self-center.flex-grow-1')
                for item in exact_items[:3]:
                    try:
                        edu_data: Dict[str, Any] = {}
                        school_elem = await item.query_selector('.t-bold span[aria-hidden="true"], h3, .t-bold')
                        if school_elem:
                            s = (await school_elem.text_content()).strip()
                            if s:
                                edu_data['school'] = s
                        degree_elem = await item.query_selector('.t-normal span[aria-hidden="true"], h4, .t-normal')
                        if degree_elem:
                            deg = (await degree_elem.text_content()).strip()
                            if deg:
                                edu_data['degree'] = deg
                        duration_elem = await item.query_selector('.t-black--light span[aria-hidden="true"], .t-black--light')
                        if duration_elem:
                            dur = (await duration_elem.text_content()).strip()
                            if dur:
                                edu_data['duration'] = dur
                        if edu_data.get('school'):
                            education.append(edu_data)
                    except Exception:
                        continue
                if education:
                    print(f"✅ Extracted {len(education)} education entries (exact selectors)")
                    return education
            except Exception:
                pass

            await self._open_detail(
                page,
                profile_root,
                'details/education/',
                'ul.pvs-list__paged-list-items'
            )

            edu_items = await page.query_selector_all('ul.pvs-list__paged-list-items > li, li.pvs-list__item--line-separated, .pvs-entity')
            
            print(f"✅ Found {len(edu_items)} education items")
            
            for item in edu_items[:3]:  # Limit to 3 items
                try:
                    edu_data = {}
                    
                    # School name - multiple selector options
                    school_selectors = [
                        '.t-bold span[aria-hidden="true"]',
                        '.pvs-entity__caption-wrapper .t-bold span',
                        '[data-field="education_school_logo"] + div .t-bold span',
                        '.pv-entity__summary-info .t-bold span',
                        '.education-item__school span',
                        '.t-16 .t-bold span[aria-hidden="true"]'
                    ]
                    
                    for school_sel in school_selectors:
                        school_elem = await item.query_selector(school_sel)
                        if school_elem:
                            school = (await school_elem.text_content()).strip()
                            if school and len(school) > 2:
                                edu_data['school'] = school
                                break
                    
                    # Degree - multiple selector options
                    degree_selectors = [
                        '.t-normal span[aria-hidden="true"]',
                        '.pvs-entity__caption-wrapper .t-normal span',
                        '.pv-entity__secondary-title span',
                        '.education-item__degree span',
                        '.t-14 .t-normal span[aria-hidden="true"]'
                    ]
                    
                    for degree_sel in degree_selectors:
                        degree_elem = await item.query_selector(degree_sel)
                        if degree_elem:
                            degree = (await degree_elem.text_content()).strip()
                            if degree and len(degree) > 2:
                                edu_data['degree'] = degree
                                break
                    
                    # Duration - multiple selector options
                    duration_selectors = [
                        '.t-black--light span[aria-hidden="true"]',
                        '.pvs-entity__caption-wrapper .t-black--light span',
                        '.pv-entity__dates span',
                        '.education-item__duration span',
                        '.t-12 .t-black--light span[aria-hidden="true"]'
                    ]
                    
                    for duration_sel in duration_selectors:
                        duration_elem = await item.query_selector(duration_sel)
                        if duration_elem:
                            duration = (await duration_elem.text_content()).strip()
                            if duration and len(duration) > 2:
                                edu_data['duration'] = duration
                                break
                    
                    # Relaxed acceptance: include if at least school OR degree is present
                    if edu_data and (edu_data.get('school') or edu_data.get('degree')):
                        school = (edu_data.get('school') or '').strip()
                        degree = (edu_data.get('degree') or '').strip()
                        low = (school + ' ' + degree).lower()

                        exclude_keywords = [
                            'top skills', 'skills', 'skill', 'endorsement', 'endorsed', 'show more',
                            'see all', 'view more', 'expand', 'collapse', 'programming language',
                            'activity', 'posts', 'likes', 'comments', 'shares', 'reactions'
                        ]
                        is_excluded = any(k in low for k in exclude_keywords)

                        if not (school.startswith('•') or degree.startswith('•')) and not is_excluded:
                            education.append(edu_data)
                        
                except Exception as e:
                    print(f"⚠️ Error extracting education item: {e}")
                    continue
            
            print(f"✅ Extracted {len(education)} education entries")
            
        except Exception as e:
            print(f"⚠️ Error extracting education: {e}")
        
        return education
    
    async def extract_activity_posts(self, page, profile_root: str) -> List[Dict]:
        """Extract recent activity posts."""
        posts = []
        
        try:
            # Navigate to activity page from profile root (avoid stale detail URLs)
            activity_url = profile_root + 'recent-activity/all/'
            await page.goto(activity_url, wait_until='domcontentloaded', timeout=self.timeout)
            await page.wait_for_timeout(2500)
            
            # Scroll to load content
            await self._progressive_scroll(page, steps=8)
            
            # Use the new individual post selector provided by user
            post_selector = '#ember735 > div > div > div.fie-impression-container > div.gBZADplBUhjJEuwClhfklXoBpUswoQqQzDCykjU > div > div > span > span'
            
            # Also try fallback selectors
            fallback_selectors = [
                'article.update-components-update',
                'div.recent-activity-update',
                'div.feed-shared-update-v2',
                'div.occludable-update'
            ]
            
            # Try the new selector first
            try:
                post_items = await page.query_selector_all(post_selector)
                if post_items:
                    print(f"✅ Found {len(post_items)} posts with new selector")
                    
                    for item in post_items[:4]:  # Limit to 4 posts
                        try:
                            post_data = {}
                            
                            # Post text
                            text_elem = await item.query_selector('.feed-shared-text, .update-components-text, .break-words, span[dir="ltr"]')
                            if text_elem:
                                text = (await text_elem.text_content()).strip()
                                if text and len(text) > 10:
                                    post_data['text'] = text
                            
                            # Post date
                            date_elem = await item.query_selector('.feed-shared-actor__sub-description, .update-components-actor__sub-description, time')
                            if date_elem:
                                date = (await date_elem.text_content()).strip()
                                if date and len(date) > 2:
                                    post_data['date'] = date
                            
            # Images disabled by requirement
            # Do not scrape or include images in activity posts
                            
                            if post_data and len(post_data) >= 1:
                                posts.append(post_data)
                                
                        except Exception as e:
                            print(f"⚠️ Error extracting post: {e}")
                            continue
                    
                    if posts:
                        print(f"✅ Extracted {len(posts)} activity posts with new selector")
                        return posts
                        
            except Exception as e:
                print(f"⚠️ Error with new selector: {e}")
            
            # Fallback to original selectors
            for selector in fallback_selectors:
                try:
                    post_items = await page.query_selector_all(selector)
                    if post_items:
                        print(f"✅ Found {len(post_items)} posts with fallback selector: {selector}")
                        
                        for item in post_items[:4]:  # Limit to 4 posts
                            try:
                                post_data = {}
                                
                                # Post text
                                text_elem = await item.query_selector('.feed-shared-text, .update-components-text, .break-words, span[dir="ltr"]')
                                if text_elem:
                                    text = (await text_elem.text_content()).strip()
                                    if text and len(text) > 10:
                                        post_data['text'] = text
                                
                                # Post date
                                date_elem = await item.query_selector('.feed-shared-actor__sub-description, .update-components-actor__sub-description, time')
                                if date_elem:
                                    date = (await date_elem.text_content()).strip()
                                    if date and len(date) > 2:
                                        post_data['date'] = date
                                
            # Images disabled by requirement
                                
                                if post_data and len(post_data) >= 1:
                                    posts.append(post_data)
                                    
                            except Exception as e:
                                print(f"⚠️ Error extracting post: {e}")
                                continue
                        
                        if posts:
                            break
                            
                except:
                    continue
            
            print(f"✅ Extracted {len(posts)} activity posts")
            
        except Exception as e:
            print(f"⚠️ Error extracting activity posts: {e}")
        
        return posts
    
    async def extract_recommendations(self, page, profile_root: str) -> List[Dict]:
        """Extract recommendations."""
        recommendations = []
        
        try:
            # Navigate to recommendations page
            rec_url = profile_root + 'details/recommendations/'
            await page.goto(rec_url, wait_until='domcontentloaded', timeout=self.timeout)
            await page.wait_for_timeout(3000)
            
            # Scroll to load content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            
            rec_items = await page.query_selector_all('.pvs-list__paged-list-items > li')
            
            print(f"✅ Found {len(rec_items)} recommendation items")
            
            for item in rec_items[:5]:  # Limit to 5 recommendations
                try:
                    rec_data = {}
                    
                    # Recommender name
                    name_elem = await item.query_selector('.t-bold span[aria-hidden="true"]')
                    if name_elem:
                        name = (await name_elem.text_content()).strip()
                        if name and len(name) > 2:
                            rec_data['recommender_name'] = name
                    
                    # Recommender title
                    title_elem = await item.query_selector('.t-normal span[aria-hidden="true"]')
                    if title_elem:
                        title = (await title_elem.text_content()).strip()
                        if title and len(title) > 2:
                            rec_data['recommender_title'] = title
                    
                    # Recommendation text
                    text_elem = await item.query_selector('.pv-shared-text-with-see-more span[aria-hidden="true"]')
                    if text_elem:
                        text = (await text_elem.text_content()).strip()
                        if text and len(text) > 10:
                            rec_data['recommendation_text'] = text
                    
                    if rec_data and len(rec_data) >= 2:
                        recommendations.append(rec_data)
                        
                except Exception as e:
                    print(f"⚠️ Error extracting recommendation: {e}")
                    continue
            
            print(f"✅ Extracted {len(recommendations)} recommendations")
            
        except Exception as e:
            print(f"⚠️ Error extracting recommendations: {e}")
        
        return recommendations
    
    async def save_profile_data(self, profile_data: Dict, filename: str = None) -> str:
        """Save profile data to JSON file."""
        try:
            os.makedirs('scraped_profiles', exist_ok=True)
            
            if not filename:
                name = profile_data.get('name', 'unknown').replace(' ', '_').lower()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"scraped_profiles/linkedin_profile_{name}_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Profile data saved to: {filename}")
            return filename
            
        except Exception as e:
            print(f"❌ Error saving profile data: {e}")
            return ""

async def main():
    """Main function to run the scraper."""
    import sys
    
    profile_url = None
    if len(sys.argv) > 1:
        profile_url = sys.argv[1].strip()
    
    if not profile_url:
        profile_url = input("Enter LinkedIn profile URL to scrape: ").strip()
    
    if not profile_url:
        print("❌ No profile URL provided")
        return
    
    scraper = LinkedInProfileScraper(headless=False)
    profile_data = await scraper.scrape_profile(profile_url)
    
    if profile_data and 'error' not in profile_data:
        filename = await scraper.save_profile_data(profile_data)
        
        print("\n✅ Successfully scraped profile:")
        print(f"   👤 Name: {profile_data.get('name', 'N/A')}")
        print(f"   💼 Headline: {profile_data.get('headline', 'N/A')}")
        print(f"   📍 Location: {profile_data.get('location', 'N/A')}")
        print(f"   📝 About section: {'✅' if profile_data.get('about') else '❌'}")
        print(f"   📱 Activity posts: {len(profile_data.get('activity_posts', []))} posts")
        print(f"   💼 Work experience: {len(profile_data.get('experience', []))} positions")
        print(f"   🎓 Education: {len(profile_data.get('education', []))} entries")
        print(f"   💾 Data saved to: {filename}")
    else:
        print(f"❌ Failed to scrape profile: {profile_data.get('error', 'Unknown error')}")

if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.run(main())
    else:
        asyncio.run(main())
