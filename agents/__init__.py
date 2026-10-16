"""Mercury Mesh agents package.

Three agent kinds, one shared language:
  - sourcing  -> finds hiring managers / recruiters / vendors, publishes leads
  - manager   -> scores, prioritizes, dispatches, learns, notifies the human
  - voice     -> Pipecat-based callers that pitch the candidate and book interviews

They communicate ONLY through the EventBus (agents/bus.py) using the event
catalog in agents/models.py. No direct imports between agent kinds.
"""
