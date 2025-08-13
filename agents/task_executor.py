import os
import asyncio
import logging
from typing import List, Dict, Optional, Any
from groq import Groq
from scrapers.linkedin_scraper import LinkedInScraper
import json
from pydantic import BaseModel
import time
import re

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source: str
    relevance_score: float = 0.0

class ScrapedData(BaseModel):
    profile_url: str
    name: str
    headline: str
    location: str
    summary: str
    experience: List[Dict] = []
    skills: List[str] = []
    education: List[Dict] = []
    contact_info: Dict = {}
    scraped_at: str
    source: str

class TaskExecutorAgent:
    def __init__(self, groq_api_key: str):
        self.groq_client = Groq(api_key=groq_api_key)
        self.logger = logging.getLogger(__name__)
        self.search_results: List[SearchResult] = []
        self.scraped_data: List[ScrapedData] = []
        self.last_api_call = 0
        self.rate_limit_delay = 3
        self.max_retries = 2
        self.user_input = None
        # Persist last search context (answer/sources/linkedin)
        self.last_search_context: Dict[str, Any] = {"answer": "", "sources": [], "linkedin_profiles": []}
    
    async def _rate_limit(self):
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        
        if time_since_last_call < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_call
            await asyncio.sleep(sleep_time)
        
        self.last_api_call = time.time()
    
    async def execute_tasks(self, user_input: str, max_results: int = 10) -> List[ScrapedData]:
        try:
            self.user_input = user_input
            self.logger.info("Starting task execution")
            
            task_type = self._analyze_task_type(user_input)
            
            if task_type == "linkedin_search":
                await self._execute_linkedin_search(user_input, max_results)
            elif task_type == "web_only":
                await self._execute_web_only(user_input, max_results)
            elif task_type == "web_search":
                await self._execute_web_search(user_input, max_results)
            elif task_type == "data_scraping":
                await self._execute_data_scraping(user_input, max_results)
            else:
                await self._execute_web_only(user_input, max_results)
            
            self.logger.info(f"Task execution completed. Found {len(self.scraped_data)} results")
            return self.scraped_data
            
        except Exception as e:
            self.logger.error(f"Error in task execution: {e}")
            return self.scraped_data
    
    def _analyze_task_type(self, user_input: str) -> str:
        input_lower = user_input.lower()
        
        if any(word in input_lower for word in ['linkedin', 'profile', 'professional profile', 'resume', 'cv']):
            return "linkedin_search"
        
        fact_keywords = [
            'average', 'avg', 'salary', 'salaries', 'what is', 'who is', 'define', 'definition',
            'statistics', 'stats', 'market size', 'trend', 'trends', 'overview', 'comparison', 'vs',
            'benefits', 'cons', 'pros', 'how much', 'how many', 'price', 'cost'
        ]
        if any(k in input_lower for k in fact_keywords):
            return "web_only"
        
        if any(word in input_lower for word in ['scrape', 'extract', 'data from', 'crawl']):
            return "data_scraping"
        
        if any(word in input_lower for word in ['search', 'find', 'look for']):
            return "web_search"
        
        return "web_only"
    
    async def _execute_linkedin_search(self, user_input: str, max_results: int):
        search_queries = await self._generate_search_queries(user_input, "linkedin")
        await self._perform_web_search(search_queries, max_results)
        # Try LinkedIn URLs found
        await self._scrape_linkedin_profiles(max_results)
        
        # If none found, run a site-specific pass to coerce LinkedIn URLs
        linkedin_urls = [r.url for r in self.search_results if 'linkedin.com/in/' in r.url]
        if not linkedin_urls:
            self.logger.info("No LinkedIn URLs from first pass. Running site:linkedin.com secondary search.")
            site_queries = [
                f"site:linkedin.com/in {user_input}",
                f"{user_input} site:linkedin.com/in"
            ]
            await self._perform_web_search(site_queries, max_results)
            await self._scrape_linkedin_profiles(max_results)
        
        # Also process any non-LinkedIn URLs so the workflow still produces results
        await self._scrape_other_websites(max_results)
    
    async def _execute_web_search(self, user_input: str, max_results: int):
        search_queries = await self._generate_search_queries(user_input, "web")
        await self._perform_web_search(search_queries, max_results)
        await self._scrape_other_websites(max_results)
    
    async def _execute_data_scraping(self, user_input: str, max_results: int):
        urls = self._extract_urls_from_input(user_input)
        if urls:
            await self._scrape_specific_urls(urls, max_results)
        else:
            await self._execute_generic_search(user_input, max_results)
    
    async def _execute_generic_search(self, user_input: str, max_results: int):
        search_queries = await self._generate_search_queries(user_input, "generic")
        await self._perform_web_search(search_queries, max_results)
        await self._scrape_other_websites(max_results)

    async def _execute_web_only(self, user_input: str, max_results: int):
        """Perform web search only and convert results into structured items without scraping."""
        try:
            search_queries = await self._generate_search_queries(user_input, "web")
            await self._perform_web_search(search_queries, max_results)
            
            # 1) If LinkedIn profile URLs are present, scrape them even in web_only
            linkedin_urls_present = any('linkedin.com/in/' in r.url for r in self.search_results if r.url)
            if linkedin_urls_present:
                await self._scrape_linkedin_profiles(max_results)

            # 2) Add non-LinkedIn sources as minimal entries (facts/snippets)
            count_added = 0
            for result in self.search_results:
                if count_added >= max_results:
                    break
                if not result.url:
                    continue
                if 'linkedin.com/in/' in result.url:
                    # Already scraped above; skip adding minimal duplicate
                    continue
                self.scraped_data.append(ScrapedData(
                    profile_url=result.url,
                    name=result.title or 'Unknown',
                    headline='',
                    location='',
                    summary=result.snippet or '',
                    experience=[],
                    skills=[],
                    education=[],
                    contact_info={},
                    scraped_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                    source='Compound-Beta'
                ))
                count_added += 1
        except Exception as e:
            self.logger.error(f"Error in web-only execution: {e}")
    
    def _extract_urls_from_input(self, user_input: str) -> List[str]:
        url_pattern = r'https?://[^\s]+'
        return re.findall(url_pattern, user_input)
    
    async def _generate_search_queries(self, user_input: str, search_type: str) -> List[str]:
        try:
            await self._rate_limit()
            
            if search_type == "linkedin":
                prompt = (
                    "Generate 2 queries to find LinkedIn profiles relevant to: "
                    f"{user_input}. Keep them concise. Return JSON array of strings."
                )
            elif search_type == "web":
                prompt = (
                    "Generate 2 web search queries relevant to: "
                    f"{user_input}. Keep them concise. Return JSON array of strings."
                )
            else:
                prompt = (
                    "Generate 2 search queries relevant to: "
                    f"{user_input}. Keep them concise. Return JSON array of strings."
                )
            
            response = self.groq_client.chat.completions.create(
                model="compound-beta",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            try:
                queries = json.loads(content)
                if isinstance(queries, list):
                    return queries[:2]
            except json.JSONDecodeError:
                pass
            
            return self._generate_fallback_queries(user_input, search_type)
            
        except Exception as e:
            self.logger.warning(f"API failed, using fallback queries: {e}")
            return self._generate_fallback_queries(user_input, search_type)
    
    def _generate_fallback_queries(self, user_input: str, search_type: str) -> List[str]:
        if search_type == "linkedin":
            return [f"{user_input} LinkedIn", f"{user_input} professional profile"]
        else:
            return [user_input, f"{user_input} information"]
    
    async def _perform_web_search(self, search_queries: List[str], max_results: int):
        try:
            self.logger.info(f"Executing web searches for {len(search_queries)} queries")
            
            all_results = []
            
            for i, query in enumerate(search_queries):
                self.logger.info(f"Searching query {i+1}/{len(search_queries)}: {query}")
                
                query_results = await self._execute_web_search_with_retry(query, max_results // len(search_queries))
                
                if not query_results:
                    query_results = self._create_fallback_search_results(query)
                
                all_results.extend(query_results)
                
                # Save Compound Beta API responses
                if query_results:
                    self._save_compound_beta_response(query, query_results)
                
                if i < len(search_queries) - 1:
                    await asyncio.sleep(1)
            
            self.search_results = self._deduplicate_results(all_results)
            self.logger.info(f"Web search completed. Found {len(self.search_results)} results")
            
        except Exception as e:
            self.logger.error(f"Error in web search: {e}")
            self.search_results = self._create_fallback_search_results("fallback")
    
    async def _execute_web_search_with_retry(self, query: str, max_results: int) -> List[SearchResult]:
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                
                system_prompt = (
                    "You are a comprehensive web search assistant.\n\n"
                    "Response requirements:\n"
                    "Perform a thorough web search to find the most relevant and up-to-date information.\n"
                    "Include a \"Sources\" section with at least two reputable URLs.\n"
                    "Look for LinkedIn profile URLs and include them in a separate \"LinkedIn Profiles\" section if found.\n"
                    "Format your response clearly with proper sections and structure.\n\n"
                    "Response Format:\n"
                    "Answer: [Detailed answer based on reputable sources]\n"
                    "Sources:\n"
                    "• [Reputable URL 1]\n"
                    "• [Optional additional reputable URL]\n"
                    "LinkedIn Profiles (if found):\n"
                    "• [LinkedIn profile URL 1]\n\n"
                    "Additionally, at the end of your response, include a machine-readable JSON block labeled 'RESULTS_JSON'\n"
                    "that contains: {\"results\": [{\"title\": str, \"url\": str, \"snippet\": str} ...]}.\n"
                    "Ensure the JSON is valid and includes 2-5 high-quality results with meaningful snippets."
                )

                response = self.groq_client.chat.completions.create(
                    model="compound-beta",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ],
                    max_tokens=900,
                    temperature=0.2
                )
                
                content = response.choices[0].message.content.strip()
                # Save raw response for debugging/traceability
                try:
                    self._save_compound_beta_raw(query, content)
                except Exception:
                    pass
                
                # Parse structured sections
                parsed = self._parse_structured_search_response(content)
                # Merge into agent context
                self._merge_search_context(parsed)
                # Prefer explicit per-link JSON if present
                json_results = self._extract_results_json(content)
                results: List[SearchResult] = []
                if json_results:
                    for item in json_results[: max_results or 5]:
                        results.append(SearchResult(
                            title=item.get('title', '') or item.get('url', ''),
                            url=item.get('url', ''),
                            snippet=item.get('snippet', ''),
                            source='web',
                            relevance_score=0.7
                        ))
                # Fallback to sections-derived links
                if not results:
                    for u in (parsed.get('sources') or [])[:max_results or 3]:
                        results.append(SearchResult(title=u, url=u, snippet=parsed.get('answer','')[:160], source='web', relevance_score=0.6))
                    for u in (parsed.get('linkedin_profiles') or [])[:max_results or 3]:
                        results.append(SearchResult(title=u, url=u, snippet='LinkedIn profile', source='web', relevance_score=0.7))
                results = [r for r in results if r.url]
                if results:
                    return results
                
                # Fallback: best-effort extraction of URLs from raw text
                extracted = self._extract_search_results_from_text(content, max_n=3)
                if extracted:
                    return extracted
                return []
                
            except Exception as e:
                self.logger.warning(f"Web search attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    return []
        
        return []

    def _extract_search_results_from_text(self, text: str, max_n: int = 3) -> List[SearchResult]:
        """Fallback: extract http(s) links from text when JSON is malformed."""
        try:
            import re
            urls = re.findall(r'https?://[^\s\)\]\"\'\}>]+', text)
            unique: List[str] = []
            seen = set()
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    unique.append(u)
                if len(unique) >= max_n:
                    break
            return [SearchResult(title=u, url=u, snippet='', source='web', relevance_score=0.3) for u in unique]
        except Exception:
            return []

    def _parse_structured_search_response(self, content: str) -> Dict[str, Any]:
        """Parse 'Answer', 'Sources', and 'LinkedIn Profiles' sections from structured text."""
        sections = {"answer": "", "sources": [], "linkedin_profiles": []}
        try:
            lines = [l.strip() for l in content.splitlines()]
            cur = None
            buffer: List[str] = []
            for ln in lines:
                low = ln.lower()
                if low.startswith('answer:'):
                    if cur == 'answer':
                        sections['answer'] = '\n'.join(buffer).strip()
                    buffer = [ln[len('answer:'):].strip()]
                    cur = 'answer'
                elif low.startswith('sources:'):
                    if cur == 'answer':
                        sections['answer'] = '\n'.join(buffer).strip()
                    buffer = []
                    cur = 'sources'
                elif low.startswith('linkedin profiles'):
                    if cur == 'answer':
                        sections['answer'] = '\n'.join(buffer).strip()
                    buffer = []
                    cur = 'linkedin'
                else:
                    if cur == 'answer':
                        buffer.append(ln)
                    elif cur in ('sources', 'linkedin') and (ln.startswith('-') or ln.startswith('•')):
                        url = ln[1:].strip().lstrip('*•- ').strip()
                        sections['sources' if cur == 'sources' else 'linkedin_profiles'].append(url)
            if cur == 'answer' and not sections['answer']:
                sections['answer'] = '\n'.join(buffer).strip()
            # Cleanup URLs
            def clean(urls: List[str]) -> List[str]:
                return [u.split(' ')[0] for u in urls if u.startswith('http')]
            sections['sources'] = clean(sections['sources'])
            sections['linkedin_profiles'] = clean(sections['linkedin_profiles'])
        except Exception:
            pass
        return sections

    def _extract_results_json(self, content: str) -> List[Dict[str, Any]]:
        """Extract and parse the RESULTS_JSON block with results list."""
        try:
            import re, json as _json
            # Look for a JSON block following the label RESULTS_JSON
            # Capture the first {...} after the label
            m = re.search(r"RESULTS_JSON\s*\n\s*\{[\s\S]*?\}\s*$", content, re.IGNORECASE)
            if not m:
                # Try a more permissive search
                m = re.search(r"\{\s*\"results\"\s*:\s*\[.[\s\S]*?\]\s*\}", content, re.IGNORECASE)
            if not m:
                return []
            block = m.group(0)
            # Extract pure JSON from the block
            json_start = block.find('{')
            json_str = block[json_start:]
            parsed = _json.loads(json_str)
            if isinstance(parsed, dict) and isinstance(parsed.get('results'), list):
                return parsed['results']
        except Exception:
            return []
        return []

    def _merge_search_context(self, parsed: Dict[str, Any]) -> None:
        try:
            if not parsed:
                return
            if parsed.get('answer'):
                # prefer the latest non-empty answer
                self.last_search_context['answer'] = parsed.get('answer', self.last_search_context.get('answer', ''))
            # merge unique sources and linkedins
            def _merge(key):
                seen = set(self.last_search_context.get(key, []))
                for u in parsed.get(key, []) or []:
                    if u and u not in seen:
                        self.last_search_context.setdefault(key, []).append(u)
                        seen.add(u)
            _merge('sources')
            _merge('linkedin_profiles')
        except Exception:
            pass

    def _save_compound_beta_raw(self, query: str, content: str) -> None:
        try:
            import os
            from datetime import datetime
            os.makedirs('output/raw_data/compound_beta', exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            fname = f"output/raw_data/compound_beta/compound_beta_{ts}_{hash(query) % 10000}_raw.txt"
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass
    
    async def _enrich_url_with_llm(self, url: str) -> Optional[Dict[str, Any]]:
        """Ask Groq LLM to summarize and extract metadata for a URL (without visiting it)."""
        try:
            await self._rate_limit()
            prompt = (
                "Given this URL, infer a concise title and summary from the URL text and path only. "
                "Return JSON with keys: title, summary. URL: " + url
            )
            response = self.groq_client.chat.completions.create(
                model="compound-beta",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2
            )
            content = response.choices[0].message.content.strip()
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                # Fallback to wrapping raw text
                return {"title": url.split('/')[2] if '://' in url else url, "summary": content}
        except Exception as e:
            self.logger.warning(f"URL enrichment failed for {url}: {e}")
            return None

    def _create_fallback_search_results(self, query: str) -> List[SearchResult]:
        return [
            SearchResult(
                title=f"Search result for: {query}",
                url="",
                snippet=f"Search result for {query}",
                source='search',
                relevance_score=0.3
            )
        ]
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        seen_urls = set()
        unique_results = []
        
        for result in results:
            if result.url and result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)
            elif not result.url:
                unique_results.append(result)
        
        return unique_results
    
    async def _scrape_linkedin_profiles(self, max_results: int):
        try:
            self.logger.info("Starting LinkedIn profile scraping")
            
            linkedin_urls = [
                result.url for result in self.search_results 
                if 'linkedin.com/in/' in result.url
            ]
            
            if not linkedin_urls:
                self.logger.warning("No LinkedIn URLs found in search results")
                return
            
            linkedin_urls = linkedin_urls[:max_results]
            
            async with LinkedInScraper(headless=True) as scraper:
                for url in linkedin_urls:
                    try:
                        profile_data = await scraper.scrape_profile(url)
                        if profile_data:
                            scraped_data = ScrapedData(
                                profile_url=profile_data.get('profile_url', url),
                                name=profile_data.get('name', 'Unknown'),
                                headline=profile_data.get('headline', ''),
                                location=profile_data.get('location', ''),
                                summary=profile_data.get('summary', ''),
                                experience=profile_data.get('experience', []),
                                skills=profile_data.get('skills', []),
                                education=profile_data.get('education', []),
                                contact_info=profile_data.get('contact_info', {}),
                                scraped_at=profile_data.get('scraped_at', ''),
                                source='LinkedIn'
                            )
                            self.scraped_data.append(scraped_data)
                            
                    except Exception as e:
                        self.logger.error(f"Error scraping LinkedIn profile {url}: {e}")
                        continue
            
            self.logger.info(f"LinkedIn scraping completed. Scraped {len(self.scraped_data)} profiles")
            
        except Exception as e:
            self.logger.error(f"Error in LinkedIn scraping: {e}")
    
    async def _scrape_other_websites(self, max_results: int):
        try:
            other_urls = [
                result.url for result in self.search_results 
                if 'linkedin.com/in/' not in result.url and result.url
            ]
            if not other_urls:
                return
            count_added = 0
            for url in other_urls:
                if count_added >= max_results:
                    break
                try:
                    enriched = await self._enrich_url_with_llm(url)
                    title = (enriched or {}).get('title') or url
                    summary = (enriched or {}).get('summary') or ''
                    self.scraped_data.append(ScrapedData(
                        profile_url=url,
                        name=title,
                        headline='',
                        location='',
                        summary=summary[:300] + ("..." if len(summary) > 300 else ""),
                        experience=[],
                        skills=[],
                        education=[],
                        contact_info={},
                        scraped_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                        source='Compound-Beta'
                    ))
                    count_added += 1
                except Exception as e:
                    self.logger.warning(f"Enrichment failed for {url}: {e}")
                    continue
        except Exception as e:
            self.logger.error(f"Error in other website processing: {e}")
    
    async def _scrape_specific_urls(self, urls: List[str], max_results: int):
        try:
            self.logger.info(f"Scraping specific URLs: {urls}")
            
            for url in urls[:max_results]:
                try:
                    if 'linkedin.com/in/' in url:
                        async with LinkedInScraper(headless=True) as scraper:
                            profile_data = await scraper.scrape_profile(url)
                            if profile_data:
                                scraped_data = ScrapedData(
                                    profile_url=profile_data.get('profile_url', url),
                                    name=profile_data.get('name', 'Unknown'),
                                    headline=profile_data.get('headline', ''),
                                    location=profile_data.get('location', ''),
                                    summary=profile_data.get('summary', ''),
                                    experience=profile_data.get('experience', []),
                                    skills=profile_data.get('skills', []),
                                    education=profile_data.get('education', []),
                                    contact_info=profile_data.get('contact_info', {}),
                                    scraped_at=profile_data.get('scraped_at', ''),
                                    source='LinkedIn'
                                )
                                self.scraped_data.append(scraped_data)
                    else:
                        scraped_data = await self._scrape_with_firecrawl(url)
                        if scraped_data:
                            self.scraped_data.append(scraped_data)
                            
                except Exception as e:
                    self.logger.error(f"Error scraping URL {url}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in specific URL scraping: {e}")
    
    # Firecrawl removed – no generic site scraping
    
    def _save_compound_beta_response(self, query: str, results: List[SearchResult]):
        """Save Compound Beta API responses to file"""
        try:
            import os
            import json
            from datetime import datetime
            
            # Create output directory if it doesn't exist
            os.makedirs('output/raw_data/compound_beta', exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"output/raw_data/compound_beta/compound_beta_{timestamp}_{hash(query) % 10000}.json"
            
            response_data = {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "source": "compound_beta",
                "results_count": len(results),
                "results": [result.dict() for result in results]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Compound Beta response saved to: {filename}")
            
        except Exception as e:
            self.logger.error(f"Error saving Compound Beta response: {e}")
    
    # Firecrawl save removed

    def _save_compound_beta_enriched(self, url: str, data: dict):
        """Save LLM-enriched metadata for non-LinkedIn URLs"""
        try:
            import os
            import json
            from datetime import datetime
            os.makedirs('output/raw_data/compound_beta_enriched', exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"output/raw_data/compound_beta_enriched/enriched_{timestamp}_{hash(url) % 10000}.json"
            payload = {
                "url": url,
                "timestamp": datetime.now().isoformat(),
                "source": "compound_beta_enriched",
                "data": data
            }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Enriched URL metadata saved to: {filename}")
        except Exception as e:
            self.logger.error(f"Error saving enriched URL data: {e}")
