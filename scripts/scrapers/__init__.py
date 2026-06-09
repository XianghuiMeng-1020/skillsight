from scripts.scrapers.base import JobPosting, ScraperBase
from scripts.scrapers.jobsdb import JobsDbScraper
from scripts.scrapers.ctgoodjobs import CtGoodJobsScraper
from scripts.scrapers.gov_hk import GovHkScraper
from scripts.scrapers.boss_zhipin import scrape_mainland_jobs

__all__ = [
    "JobPosting",
    "ScraperBase",
    "JobsDbScraper",
    "CtGoodJobsScraper",
    "GovHkScraper",
    "scrape_mainland_jobs",
]
