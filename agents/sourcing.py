"""Sourcing agent: finds hiring managers, recruiters, and vendors.

Publishes LEAD_DISCOVERED to the bus for every new lead. Dedupe is by phone
number in the Store, so re-running discovery never double-calls anyone.

Provider notes (honest):
  - CsvLeadProvider: works today. Bring your own list (name,title,company,phone,email,timezone).
  - WebSearchLeadProvider: scaffold — wire to SerpAPI/Brave Search API to find
    "site:linkedin.com/in recruiter <city>" style results, then enrich.
  - ApolloLeadProvider: scaffold — Apollo/RocketReach have real APIs for exactly
    this (people search + phone enrichment). Needs an API key.
"""
from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import asdict

from . import models
from .bus import EventBus
from .models import Event, Lead
from .profile import score_lead
from .store import Store


class LeadProvider(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, query: str, limit: int = 50) -> list[Lead]:
        ...


class CsvLeadProvider(LeadProvider):
    """Your own curated list. CSV columns: name,title,company,phone,email,timezone,notes."""
    name = "csv"

    def __init__(self, path: str):
        self.path = path

    def search(self, query: str = "", limit: int = 50) -> list[Lead]:
        leads: list[Lead] = []
        with open(self.path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("phone"):
                    continue
                leads.append(Lead(
                    name=row.get("name", ""), title=row.get("title", ""),
                    company=row.get("company", ""), phone=row["phone"].strip(),
                    email=row.get("email", ""), timezone=row.get("timezone", "America/Chicago"),
                    notes=row.get("notes", ""), source=f"csv:{self.path}",
                ))
                if len(leads) >= limit:
                    break
        return leads


class WebSearchLeadProvider(LeadProvider):
    """Scaffold: implement with a search API (SerpAPI / Brave) that returns
    recruiter profile URLs, then an enrichment step for phones."""
    name = "websearch"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def search(self, query: str, limit: int = 50) -> list[Lead]:
        raise NotImplementedError(
            "Wire WebSearchLeadProvider.search to a search API (e.g. SerpAPI) and "
            "a phone-enrichment API (e.g. Apollo). See ARCHITECTURE.md."
        )


class ApolloLeadProvider(LeadProvider):
    """Scaffold for Apollo.io / RocketReach style enrichment APIs."""
    name = "apollo"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def search(self, query: str, limit: int = 50) -> list[Lead]:
        raise NotImplementedError(
            "Set APOLLO_API_KEY and implement people-search + phone enrichment "
            "against the Apollo API. See ARCHITECTURE.md."
        )


class SourcingAgent:
    def __init__(self, bus: EventBus, store: Store, providers: list[LeadProvider]):
        self.bus = bus
        self.store = store
        self.providers = providers

    async def discover(self, query: str, limit: int = 50) -> list[Lead]:
        """Run all providers, dedupe, score, persist, and announce each lead."""
        found: list[Lead] = []
        for provider in self.providers:
            try:
                found.extend(provider.search(query, limit))
            except NotImplementedError:
                continue  # scaffold provider not wired yet — skip, don't crash
        new_leads: list[Lead] = []
        for lead in found:
            lead.score = score_lead(lead)
            existing = self.store.get_lead(lead.id)  # new id each time; dedupe by phone
            self.store.save_lead(lead)  # upsert on phone
            new_leads.append(lead)
            await self.bus.publish(Event(
                type=models.LEAD_DISCOVERED, payload={"lead": asdict(lead)}))
        return new_leads
