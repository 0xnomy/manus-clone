import asyncio
import logging
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
import argparse
import json
from datetime import datetime
import time
import sys
import hashlib
import pandas as pd

from agents.task_executor import TaskExecutorAgent
from agents.task_updater import TaskUpdaterAgent, TaskStatus, TaskType
from agents.report_generator import ReportGeneratorAgent

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('manus_clone.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ManusCloneWorkflow:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.task_executor_agent = TaskExecutorAgent(self.groq_api_key)
        self.task_updater_agent = TaskUpdaterAgent()
        self.report_generator_agent = ReportGeneratorAgent(self.groq_api_key)
        
        self.user_input = None
        self.scraped_data = []
        self.cleaned_data = None
        self.final_report = None
        
        # Create output directories
        self._create_output_directories()
    
    def _create_output_directories(self):
        directories = [
            'output',
            'output/raw_data',
            'output/raw_data/linkedin',
            'output/raw_data/compound_beta',
            'output/raw_data/compound_beta_enriched',
            'output/raw_data/firecrawl',
            'output/cleaned_data',
            'output/reports',
            'output/charts',
            'output/logs'
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def _generate_query_hash(self, query: str) -> str:
        """Generate a hash for the query to use in filenames"""
        return hashlib.md5(query.encode()).hexdigest()[:8]
    
    def _save_raw_data(self, data: List, source: str, query: str):
        """Save raw scraped data to JSON file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            query_hash = self._generate_query_hash(query)
            
            filename = f"output/raw_data/{source}/{source}_{timestamp}_{query_hash}.json"
            
            raw_data = {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "data_count": len(data),
                "data": [item.dict() if hasattr(item, 'dict') else item for item in data]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(raw_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Raw data saved to: {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error saving raw data: {e}")
            return None
    
    def _save_cleaned_data(self, data: pd.DataFrame, query: str):
        """Save cleaned data to CSV file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            query_hash = self._generate_query_hash(query)
            
            filename = f"output/cleaned_data/cleaned_{timestamp}_{query_hash}.csv"
            
            data.to_csv(filename, index=False, encoding='utf-8')
            
            self.logger.info(f"Cleaned data saved to: {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error saving cleaned data: {e}")
            return None
    
    def _save_report(self, report: str, query: str):
        """Save generated report to file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            query_hash = self._generate_query_hash(query)
            
            filename = f"output/reports/report_{timestamp}_{query_hash}.md"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            
            self.logger.info(f"Report saved to: {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error saving report: {e}")
            return None
    
    def print_header(self):
        print("\n" + "="*80)
        print("🚀 MANUS CLONE - AI AGENT SYSTEM")
        print("="*80)
        print(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 User Request: {self.user_input}")
        print("="*80 + "\n")
    
    def print_agent_status(self, agent_name: str, status: str, message: str = "", progress: float = None):
        status_icons = {
            "starting": "🔄",
            "running": "⚡",
            "completed": "✅",
            "failed": "❌",
            "waiting": "⏳"
        }
        
        icon = status_icons.get(status, "📋")
        status_text = f"{icon} {agent_name.upper()}: {status.upper()}"
        
        if progress is not None:
            status_text += f" ({progress:.1f}%)"
        
        print(f"{status_text}")
        if message:
            print(f"   └─ {message}")
        print()
    
    def print_progress_bar(self, current: int, total: int, width: int = 50):
        progress = current / total if total > 0 else 0
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
        percentage = progress * 100
        print(f"   [{bar}] {percentage:.1f}% ({current}/{total})")
    
    async def execute_workflow(self, user_input: str, max_results: int = 10, verbose: bool = False) -> Dict:
        try:
            self.user_input = user_input
            self.task_updater_agent.reset_workflow()
            
            self.print_header()
            
            await self._step_task_execution(max_results, verbose)
            await self._step_prepare_dataframe(verbose)
            await self._step_report_generation(verbose)
            
            results = self._prepare_final_results()
            self.print_completion_summary(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")
            self.task_updater_agent.log_error("workflow", e, "Main workflow execution")
            self.print_agent_status("WORKFLOW", "failed", f"Error: {str(e)}")
            raise
    
    async def _step_task_execution(self, max_results: int, verbose: bool) -> None:
        task_id = self.task_updater_agent.create_task(
            "task_execution", 
            TaskType.LINKEDIN_SCRAPING
        )
        
        try:
            self.print_agent_status("TASK EXECUTOR", "starting", "Initializing task execution...")
            
            self.task_updater_agent.update_task_status(
                task_id, TaskStatus.IN_PROGRESS, progress_percentage=0
            )
            
            if verbose:
                print("   🔍 Analyzing task type...")
                print("   📝 Generating search queries...")
                print("   🌐 Executing web searches...")
            
            self.scraped_data = await self.task_executor_agent.execute_tasks(
                self.user_input, max_results
            )
            
            # Save raw scraped data
            if self.scraped_data:
                self._save_raw_data(self.scraped_data, "linkedin", self.user_input)
            
            self.task_updater_agent.update_task_status(
                task_id, TaskStatus.COMPLETED, progress_percentage=100,
                details={'scraped_records': len(self.scraped_data)}
            )
            
            self.print_agent_status("TASK EXECUTOR", "completed", 
                                  f"Successfully processed {len(self.scraped_data)} records")
            
            if verbose and self.scraped_data:
                print("   📊 Sample records found:")
                for i, record in enumerate(self.scraped_data[:3]):
                    print(f"      {i+1}. {record.name} - {record.headline} ({record.location})")
                if len(self.scraped_data) > 3:
                    print(f"      ... and {len(self.scraped_data) - 3} more records")
            
        except Exception as e:
            self.task_updater_agent.log_error(task_id, e, "Task execution")
            self.print_agent_status("TASK EXECUTOR", "failed", f"Error: {str(e)}")
            raise
    
    async def _step_prepare_dataframe(self, verbose: bool) -> None:
        task_id = self.task_updater_agent.create_task(
            "prepare_dataframe", 
            TaskType.DATA_CLEANING
        )
        
        try:
            self.print_agent_status("DATAFRAME", "starting", "Converting scraped data to DataFrame...")
            
            self.task_updater_agent.update_task_status(
                task_id, TaskStatus.IN_PROGRESS, progress_percentage=0
            )
            
            if verbose:
                print("   🧾 Building minimal DataFrame...")
            
            # Build a minimal DataFrame directly from scraped data
            # Keep only fields used by report generator and downstream
            records = []
            for item in self.scraped_data:
                # Support pydantic model or dict
                row = item.dict() if hasattr(item, 'dict') else dict(item)
                records.append({
                    'profile_url': row.get('profile_url', ''),
                    'name': row.get('name', 'Unknown'),
                    'headline': row.get('headline', ''),
                    'location': row.get('location', ''),
                    'summary': row.get('summary', ''),
                    'experience': row.get('experience', []),
                    'skills': row.get('skills', []),
                    'education': row.get('education', []),
                    'source': row.get('source', 'Unknown')
                })
            df = pd.DataFrame(records)
            # Derive all_skills if possible
            if not df.empty:
                def to_list_safe(v):
                    if isinstance(v, list):
                        return v
                    return []
                df['all_skills'] = df['skills'].apply(to_list_safe)
            # If we have a narrative answer from web-only search, inject as a single record for reporting
            try:
                from agents.task_executor import TaskExecutorAgent
                if hasattr(self.task_executor_agent, 'last_search_context'):
                    ans = self.task_executor_agent.last_search_context.get('answer')
                    if ans and (df is None or df.empty):
                        df = pd.DataFrame([
                            {
                                'profile_url': '',
                                'name': 'Web Answer',
                                'headline': '',
                                'location': '',
                                'summary': ans,
                                'experience': [],
                                'skills': [],
                                'education': [],
                                'source': 'Compound-Beta'
                            }
                        ])
            except Exception:
                pass

            self.cleaned_data = df
            
            # Save prepared data
            if self.cleaned_data is not None and not self.cleaned_data.empty:
                self._save_cleaned_data(self.cleaned_data, self.user_input)
            
            self.task_updater_agent.update_task_status(
                task_id, TaskStatus.COMPLETED, progress_percentage=100,
                details={'cleaned_records': len(self.cleaned_data) if self.cleaned_data is not None else 0}
            )
            
            self.print_agent_status("DATAFRAME", "completed", 
                                  f"Prepared {len(self.cleaned_data) if self.cleaned_data is not None else 0} records for reporting")
            
            if verbose and self.cleaned_data is not None:
                print("   📊 DataFrame preview:")
                print(f"      - Records: {len(self.cleaned_data)}")
                print(f"      - Columns: {list(self.cleaned_data.columns)}")
            
        except Exception as e:
            self.task_updater_agent.log_error(task_id, e, "Prepare DataFrame")
            self.print_agent_status("DATAFRAME", "failed", f"Error: {str(e)}")
            raise
    
    async def _step_report_generation(self, verbose: bool) -> None:
        task_id = self.task_updater_agent.create_task(
            "report_generation", 
            TaskType.REPORT_GENERATION
        )
        
        try:
            self.print_agent_status("REPORT GENERATOR", "starting", "Initializing report generation...")
            
            self.task_updater_agent.update_task_status(
                task_id, TaskStatus.IN_PROGRESS, progress_percentage=0
            )
            
            if verbose:
                print("   🤖 Generating AI analysis...")
                print("   📊 Creating summary statistics...")
                print("   📈 Generating visualizations...")
            
            if self.cleaned_data is None or self.cleaned_data.empty:
                self.logger.warning("No data available for report generation")
                self.final_report = "# No Data Report\n\nNo data was available for analysis."
            else:
                report_format = {
                    'include_charts': False,
                    'include_summary': True,
                    'format': 'markdown'
                }
                
                # Pass search context to the report generator for better summaries
                ctx = {}
                try:
                    ctx = {
                        'user_input': self.user_input,
                        'answer': getattr(self.task_executor_agent, 'last_search_context', {}).get('answer', ''),
                        'search_answer': getattr(self.task_executor_agent, 'last_search_context', {}).get('answer', ''),
                        'sources': getattr(self.task_executor_agent, 'last_search_context', {}).get('sources', []),
                        'linkedin_profiles': getattr(self.task_executor_agent, 'last_search_context', {}).get('linkedin_profiles', []),
                    }
                except Exception:
                    pass

                self.final_report = self.report_generator_agent.generate_report(
                    self.cleaned_data, report_format, context=ctx
                )
                
                # Save generated report
                if self.final_report:
                    self._save_report(self.final_report, self.user_input)
            
            self.task_updater_agent.update_task_status(
                task_id, TaskStatus.COMPLETED, progress_percentage=100,
                details={'report_length': len(self.final_report) if self.final_report else 0}
            )
            
            self.print_agent_status("REPORT GENERATOR", "completed", 
                                  f"Successfully generated report ({len(self.final_report) if self.final_report else 0} characters)")
            
            if verbose and self.final_report:
                print("   📄 Report preview:")
                preview = self.final_report[:200] + "..." if len(self.final_report) > 200 else self.final_report
                print(f"      {preview}")
            
        except Exception as e:
            self.task_updater_agent.log_error(task_id, e, "Report generation")
            self.print_agent_status("REPORT GENERATOR", "failed", f"Error: {str(e)}")
            raise
    
    def _prepare_final_results(self) -> Dict:
        return {
            'user_input': self.user_input,
            'scraped_data_count': len(self.scraped_data),
            'cleaned_data_count': len(self.cleaned_data) if self.cleaned_data is not None else 0,
            'report_generated': self.final_report is not None,
            'final_report': self.final_report,
            'final_report_preview': self.final_report[:300] + "..." if self.final_report and len(self.final_report) > 300 else self.final_report,
            'workflow_status': 'completed',
            'timestamp': datetime.now().isoformat()
        }
    
    def print_completion_summary(self, results: Dict) -> None:
        print("\n" + "="*80)
        print("🎉 WORKFLOW COMPLETED SUCCESSFULLY")
        print("="*80)
        print(f"📊 Results Summary:")
        print(f"   • Records scraped: {results['scraped_data_count']}")
        print(f"   • Records cleaned: {results['cleaned_data_count']}")
        print(f"   • Report generated: {'✅ Yes' if results['report_generated'] else '❌ No'}")
        print(f"   • Report length: {len(results['final_report']) if results['final_report'] else 0} characters")
        print(f"   • Completion time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Manus Clone - AI Agent System")
    parser.add_argument("-i", "--input", required=True, help="Natural language input describing the task")
    parser.add_argument("-m", "--max-results", type=int, default=10, help="Maximum number of results to collect")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress all output except errors")
    parser.add_argument("-o", "--output", help="Output file for the report")
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    try:
        workflow = ManusCloneWorkflow()
        
        async def run_workflow():
            results = await workflow.execute_workflow(
                args.input, 
                max_results=args.max_results, 
                verbose=args.verbose
            )
            
            if args.output and results['final_report']:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(results['final_report'])
                print(f"📄 Report saved to: {args.output}")
            
            return results
        
        results = asyncio.run(run_workflow())
        
        if not args.quiet:
            print("\n✅ Workflow completed successfully!")
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        if not args.quiet:
            print(f"\n❌ Workflow failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
