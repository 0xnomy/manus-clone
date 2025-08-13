from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)

class SearchTerm(BaseModel):
    """Represents a search term with type and value"""
    type: str = Field(..., description="Type of search term (role, skill, location, company)")
    value: str = Field(..., description="The actual search term value")
    priority: int = Field(default=1, description="Priority level (1-5)")

class TargetWebsite(BaseModel):
    """Represents a target website for scraping"""
    name: str = Field(..., description="Website name")
    url: str = Field(..., description="Base URL of the website")
    priority: int = Field(default=1, description="Priority level (1-5)")

class ReportFormat(BaseModel):
    """Represents the required report format"""
    format_type: str = Field(default="markdown", description="Report format (markdown, json, csv)")
    include_charts: bool = Field(default=True, description="Whether to include charts")
    include_summary: bool = Field(default=True, description="Whether to include summary")

class ParsedRequest(BaseModel):
    """Structured representation of the parsed user request"""
    search_terms: List[SearchTerm] = Field(..., description="List of search terms")
    target_websites: List[TargetWebsite] = Field(..., description="List of target websites")
    report_format: ReportFormat = Field(default=ReportFormat(), description="Required report format")
    max_results: int = Field(default=10, description="Maximum number of results to collect")
    include_contact_info: bool = Field(default=False, description="Whether to include contact information")

class UserRequirementAnalysisAgent:
    """Agent responsible for parsing user input into structured subtasks"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_request(self, user_input: str) -> ParsedRequest:
        """
        Parse user input into structured subtasks
        
        Args:
            user_input: Raw user input string
            
        Returns:
            ParsedRequest: Structured representation of the request
        """
        try:
            self.logger.info(f"Parsing user request: {user_input}")
            
            # Extract search terms
            search_terms = self._extract_search_terms(user_input)
            
            # Determine target websites
            target_websites = self._determine_target_websites(user_input)
            
            # Determine report format
            report_format = self._determine_report_format(user_input)
            
            # Extract other parameters
            max_results = self._extract_max_results(user_input)
            include_contact_info = self._extract_contact_info_preference(user_input)
            
            parsed_request = ParsedRequest(
                search_terms=search_terms,
                target_websites=target_websites,
                report_format=report_format,
                max_results=max_results,
                include_contact_info=include_contact_info
            )
            
            self.logger.info(f"Successfully parsed request: {parsed_request}")
            return parsed_request
            
        except Exception as e:
            self.logger.error(f"Error parsing user request: {e}")
            raise
    
    def _extract_search_terms(self, user_input: str) -> List[SearchTerm]:
        """Extract search terms from user input"""
        search_terms = []
        
        # Common job roles
        job_roles = [
            "software engineer", "data scientist", "product manager", "designer",
            "marketing manager", "sales representative", "analyst", "developer",
            "architect", "consultant", "manager", "director", "vp", "ceo"
        ]
        
        # Common skills
        skills = [
            "python", "javascript", "java", "react", "node.js", "sql", "aws",
            "machine learning", "ai", "data analysis", "project management",
            "agile", "scrum", "marketing", "sales", "design", "ui/ux"
        ]
        
        # Common locations
        locations = [
            "san francisco", "new york", "london", "seattle", "austin", "boston",
            "chicago", "los angeles", "remote", "hybrid", "onsite"
        ]
        
        # Extract roles
        for role in job_roles:
            if role.lower() in user_input.lower():
                search_terms.append(SearchTerm(type="role", value=role, priority=3))
        
        # Extract skills
        for skill in skills:
            if skill.lower() in user_input.lower():
                search_terms.append(SearchTerm(type="skill", value=skill, priority=2))
        
        # Extract locations
        for location in locations:
            if location.lower() in user_input.lower():
                search_terms.append(SearchTerm(type="location", value=location, priority=4))
        
        # If no specific terms found, create a general search
        if not search_terms:
            search_terms.append(SearchTerm(type="general", value=user_input, priority=1))
        
        return search_terms
    
    def _determine_target_websites(self, user_input: str) -> List[TargetWebsite]:
        """Determine target websites based on user input"""
        websites = []
        
        # Always include LinkedIn for professional profiles
        websites.append(TargetWebsite(
            name="LinkedIn",
            url="https://www.linkedin.com",
            priority=1
        ))
        
        # Add other job boards if mentioned
        if any(term in user_input.lower() for term in ["indeed", "job board"]):
            websites.append(TargetWebsite(
                name="Indeed",
                url="https://www.indeed.com",
                priority=2
            ))
        
        if any(term in user_input.lower() for term in ["glassdoor", "reviews"]):
            websites.append(TargetWebsite(
                name="Glassdoor",
                url="https://www.glassdoor.com",
                priority=3
            ))
        
        return websites
    
    def _determine_report_format(self, user_input: str) -> ReportFormat:
        """Determine report format based on user input"""
        format_type = "markdown"  # Default
        include_charts = True
        include_summary = True
        
        if "json" in user_input.lower():
            format_type = "json"
        elif "csv" in user_input.lower():
            format_type = "csv"
        
        if "no charts" in user_input.lower() or "without charts" in user_input.lower():
            include_charts = False
        
        if "no summary" in user_input.lower() or "without summary" in user_input.lower():
            include_summary = False
        
        return ReportFormat(
            format_type=format_type,
            include_charts=include_charts,
            include_summary=include_summary
        )
    
    def _extract_max_results(self, user_input: str) -> int:
        """Extract maximum number of results from user input"""
        import re
        
        # Look for numbers followed by words like "results", "profiles", etc.
        patterns = [
            r'(\d+)\s*(?:results?|profiles?|people)',
            r'find\s+(\d+)\s*',
            r'get\s+(\d+)\s*'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, user_input.lower())
            if match:
                return min(int(match.group(1)), 50)  # Cap at 50
        
        return 10  # Default
    
    def _extract_contact_info_preference(self, user_input: str) -> bool:
        """Extract whether user wants contact information"""
        contact_indicators = [
            "contact", "email", "phone", "reach out", "connect",
            "contact information", "contact details"
        ]
        
        return any(indicator in user_input.lower() for indicator in contact_indicators)
