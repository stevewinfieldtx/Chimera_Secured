#!/usr/bin/env python3
"""
Seed the background corpus.

Three modes:
  1. --from-enron    Pull from a populated Enron Postgres DB (best quality)
  2. --generate      Generate a diverse synthetic corpus (no DB needed — DEFAULT)
  3. --from-file F   Load from a newline-delimited text file

The generated corpus uses 40+ templates across 8 formality levels, 12 topics,
and 6 structural styles to produce 500+ diverse email-shaped texts. This is
good enough to train classifiers for pilot deployments. For production, use
--from-enron with the full Enron dataset.

Usage:
    python scripts/seed_background.py                      # generate 500 texts
    python scripts/seed_background.py --size 2000           # generate 2000
    python scripts/seed_background.py --from-enron          # pull from Postgres
    python scripts/seed_background.py --from-file corpus.txt

The output goes to CPA_BACKGROUND_CORPUS (see config.py).
Safe to re-run; rebuilds from scratch each time.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ---- Diverse corpus generator ------------------------------------------

# Templates organized by style/formality. Each tuple: (template, formality_tier)
# The generator picks randomly, fills in variables, and produces varied output.

GREETINGS = [
    "", "", "",  # no greeting (common)
    "Hi {name},\n\n",
    "Hey {name},\n\n",
    "Hello {name},\n\n",
    "Good morning {name},\n\n",
    "Good afternoon,\n\n",
    "Dear {name},\n\n",
    "{name},\n\n",
    "Hi team,\n\n",
    "Hey everyone,\n\n",
    "All,\n\n",
]

CLOSERS = [
    "", "", "",  # no closer
    "\n\nThanks,\n{sender}",
    "\n\nBest,\n{sender}",
    "\n\nRegards,\n{sender}",
    "\n\nBest regards,\n{sender}",
    "\n\nThanks so much,\n{sender}",
    "\n\nCheers,\n{sender}",
    "\n\nTalk soon,\n{sender}",
    "\n\nLet me know.\n\n{sender}",
    "\n\nSincerely,\n{sender}",
]

NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Quinn", "Avery",
    "Blake", "Drew", "Cameron", "Riley", "Parker", "Hayden", "Reese",
    "Jamie", "Chris", "Sam", "Pat", "Robin", "Dana", "Lee", "Kim",
]

SENDERS = [
    "Mike", "Sarah", "David", "Lisa", "James", "Rachel", "Tom",
    "Jennifer", "Brian", "Amanda", "Kevin", "Emily", "Mark", "Laura",
    "Steve", "Michelle", "Dan", "Karen", "Jeff", "Nicole", "Greg", "Amy",
]

# ---- Template pools by category ----

PROJECT_TEMPLATES = [
    "Just wanted to give you a quick update on the {project} project. We've made solid progress this week — the {component} is about {pct}% complete and we're on track for the {timeframe} deadline. {detail} Let me know if you have any questions.",
    "Following up on our conversation about {project}. I've been thinking about the approach and I believe we should {action}. The main risk is {risk}, but I think we can mitigate that by {mitigation}. What do you think?",
    "The {project} deliverable is ready for your review. I've attached the latest version which includes {changes}. The key things I'd like your feedback on are {feedback_items}. Happy to walk through it on a call if that's easier.",
    "Quick status on {project}: we hit a snag with {issue}. It's not a showstopper but it will push the {component} delivery by about {delay}. I've already {action_taken} and should have a fix by {fix_date}. Will keep you posted.",
    "I need to loop you in on a decision regarding {project}. We have two options: {option_a}, or {option_b}. I'm leaning toward the first option because {reason}. Can we discuss this at our next sync?",
    "Wrapping up {project} phase one. Final numbers: {metric_a}, {metric_b}, and {metric_c}. Overall I'm {sentiment} with the results — {assessment}. Phase two kicks off {start_date} and will focus on {next_focus}.",
]

MEETING_TEMPLATES = [
    "Can we set up time this week to discuss {topic}? I'm free {availability}. Should take about {duration} minutes. {context}",
    "Thanks for the meeting earlier. To summarize what we agreed on: {summary}. I'll take the lead on {owner_items} and you'll handle {their_items}. Let's check in again {next_meeting}.",
    "Heads up — I need to reschedule our {meeting_type} from {original_time} to {new_time}. {reason} Same agenda, just a different slot. Does that work for you?",
    "For tomorrow's {meeting_type}, here's what I'd like to cover: {agenda}. If there's anything you'd like to add, let me know before end of day. I'll share the deck in the morning.",
]

FEEDBACK_TEMPLATES = [
    "I reviewed the {deliverable} you sent over. Overall it looks {quality}. A few thoughts: {thought_1}. Also, {thought_2}. {thought_3} Let me know if you want to discuss any of this.",
    "Great work on {deliverable}. I particularly liked {strength}. One area I'd push on: {improvement}. Not a dealbreaker, but it would make the final product stronger. {additional}",
    "I have some concerns about the {deliverable}. Specifically, {concern_1}, and {concern_2}. I think we need to {recommendation} before we can move forward. Can we talk about this?",
    "The {deliverable} is approved with minor changes. {change_1} and {change_2}. Once those are in, go ahead and send it to {recipient}. Nice work pulling this together on short notice.",
]

LOGISTICS_TEMPLATES = [
    "Just confirming — the {event} is set for {date} at {location}. We're expecting {attendee_count} people. {logistics_detail} Let me know if anything changes on your end.",
    "Can you send me the {document} from the {context}? I need it for {purpose} and the deadline is {deadline}. If you can't find it, {alternative}.",
    "Reminder that {task} is due {due_date}. I know things have been hectic but this is a hard deadline because {reason}. Let me know if you need help getting it across the finish line.",
    "I'm going to be out of office {dates}. {coverage_person} will be covering for me. For anything urgent related to {project}, reach out to {backup}. I'll have limited email access.",
]

FINANCIAL_TEMPLATES = [
    "Attached are the {period} financials. Revenue came in at {revenue}, which is {variance} versus forecast. The biggest driver was {driver}. On the expense side, {expense_note}. We should discuss the implications for {planning_item} at our next review.",
    "I need approval on a {amount} purchase order for {item}. This was budgeted under {budget_line} and is needed for {reason}. The vendor is {vendor} and lead time is {lead_time}. Can you sign off?",
    "Quick note on the budget situation. We're currently {budget_status} for {period}. The main variance is {variance_source}, which {explanation}. I recommend we {recommendation} to stay on track.",
]

HR_TEMPLATES = [
    "I wanted to let you know that {person} has given their notice. Their last day is {date}. I'm working on a transition plan — key priorities are {priorities}. We should discuss whether to backfill immediately or redistribute responsibilities.",
    "Following up on our discussion about {person}'s performance. I've documented {actions_taken} and scheduled a follow-up for {date}. The key metrics we're tracking are {metrics}. I'll keep you updated on progress.",
    "We're ready to extend an offer to {person} for the {role} position. Proposed package: {compensation}. Start date would be {date}. Before I send the offer letter, do you have any concerns?",
]

CASUAL_TEMPLATES = [
    "Hey — saw the news about {topic}. Pretty interesting stuff. What do you think about {angle}? We should grab coffee and chat about it sometime.",
    "Wanted to share this with you — {share_item}. Thought you'd find it relevant given {context}. No action needed, just figured you'd want to know.",
    "Sorry for the late reply on this. Things have been crazy with {reason}. To answer your question — {answer}. Hope that helps. Shoot me a note if you need anything else.",
    "Thanks for the heads up on {topic}. I'll {action} and circle back with you {timeframe}. Appreciate you flagging it.",
    "Random question — do you know {question}? I've been looking into it for {reason} and can't find a straight answer. If you don't know offhand, no worries, I'll keep digging.",
]

FORMAL_TEMPLATES = [
    "I am writing to inform you that {formal_topic}. As per our agreement dated {date}, {obligation}. Please confirm receipt of this communication and indicate your acceptance of the terms outlined herein.",
    "Please find attached the {document_type} for your review and signature. This document has been reviewed by {reviewer} and reflects the changes discussed in our meeting of {date}. We request that the signed copy be returned by {deadline}.",
    "On behalf of {organization}, I would like to formally {action}. This decision was made after careful consideration of {factors}. We believe this course of action best serves {interests} and are committed to {commitment}.",
    "In reference to your inquiry regarding {topic}, I can confirm that {confirmation}. Should you require additional information, please do not hesitate to contact our office at your earliest convenience.",
]

TECHNICAL_TEMPLATES = [
    "The deployment went through last night. All services are green and metrics are nominal — {metric_1} and {metric_2} both within expected ranges. One thing to watch: {caveat}. I'll monitor through the week.",
    "I found the root cause of the {issue} bug. It was {root_cause}. The fix is {fix_description}. I've tested it against {test_cases} and everything passes. PR is up for review.",
    "We need to decide on the architecture for {feature}. I see two viable approaches: {approach_1}, or {approach_2}. Trade-offs are {tradeoffs}. My recommendation is {recommendation} because {reasoning}.",
    "Security scan flagged {count} items in the latest build. {critical_count} are critical: {critical_items}. The rest are low-severity and can wait. I'll have patches for the critical items by {date}.",
]


def _fill_template(template: str, rng: random.Random) -> str:
    """Fill placeholder variables with random realistic values."""
    replacements = {
        "project": rng.choice(["Aurora", "Phoenix", "Atlas", "Horizon", "Catalyst", "Pinnacle", "Vertex", "Nexus", "Quantum", "Eclipse"]),
        "component": rng.choice(["backend API", "data pipeline", "reporting module", "user dashboard", "auth system", "integration layer", "analytics engine", "notification service"]),
        "pct": str(rng.randint(40, 95)),
        "timeframe": rng.choice(["end of month", "Q3", "sprint", "November 15th", "next Friday", "mid-quarter"]),
        "detail": rng.choice([
            "The team has been executing well.",
            "We might want to add a buffer day or two for testing.",
            "I'll send a more detailed breakdown tomorrow.",
            "The only open item is the integration test suite.",
            "",
        ]),
        "action": rng.choice(["go with option B", "start with a smaller pilot", "bring in an external consultant", "accelerate the timeline", "split it into two phases"]),
        "risk": rng.choice(["timeline slippage", "scope creep", "vendor dependency", "resource constraints", "data quality issues"]),
        "mitigation": rng.choice(["setting weekly checkpoints", "adding a dedicated resource", "building in a two-week buffer", "automating the test suite"]),
        "changes": rng.choice(["the updated projections", "revised timeline", "new section on risk factors", "the competitive analysis"]),
        "feedback_items": rng.choice(["the pricing strategy and the go-to-market timeline", "the executive summary and the financial model", "the technical approach and resource plan"]),
        "issue": rng.choice(["the third-party API", "data migration", "performance testing", "a dependency conflict", "the authentication flow"]),
        "delay": rng.choice(["two days", "a week", "three to four days"]),
        "action_taken": rng.choice(["opened a ticket with the vendor", "identified a workaround", "escalated to engineering", "reallocated resources"]),
        "fix_date": rng.choice(["end of day tomorrow", "Wednesday", "Thursday at the latest"]),
        "option_a": rng.choice(["build in-house", "go with the enterprise plan", "hire a contractor", "use the existing framework"]),
        "option_b": rng.choice(["outsource to a partner", "scale back the scope", "delay until Q2", "use the open-source alternative"]),
        "reason": rng.choice(["it gives us more control long-term", "the cost difference is significant", "it aligns better with our roadmap", "the risk profile is lower"]),
        "metric_a": rng.choice(["conversion rate up 12%", "response time down to 180ms", "NPS at 72", "pipeline grew 25%"]),
        "metric_b": rng.choice(["churn held steady at 3.2%", "support tickets down 18%", "activation rate at 64%", "ARR at $2.1M"]),
        "metric_c": rng.choice(["CAC came in under budget", "retention improved by 8 points", "adoption hit 89%"]),
        "sentiment": rng.choice(["pleased", "cautiously optimistic", "satisfied", "encouraged"]),
        "assessment": rng.choice([
            "we exceeded targets on the metrics that matter most",
            "there are areas to improve but the trajectory is right",
            "the foundation is solid for scaling in the next phase",
        ]),
        "start_date": rng.choice(["next Monday", "January 6th", "after the holiday break", "early next month"]),
        "next_focus": rng.choice(["optimization and scale", "the enterprise rollout", "self-serve onboarding", "international expansion"]),
        "topic": rng.choice(["the vendor contract", "hiring priorities", "the product roadmap", "Q4 planning", "the partnership opportunity", "the compliance audit"]),
        "availability": rng.choice(["Tuesday afternoon or Wednesday morning", "anytime Thursday", "tomorrow after 2pm", "later this week"]),
        "duration": str(rng.choice([15, 20, 30, 45, 60])),
        "context": rng.choice([
            "I have some ideas I'd like to run by you.",
            "There are a few decisions we need to make before Friday.",
            "I want to make sure we're aligned before the board meeting.",
            "",
        ]),
        "summary": rng.choice([
            "we'll move forward with the revised timeline and increase the test coverage",
            "the budget is approved with the caveat that we hold 10% in reserve",
            "we're going with vendor A and the contract will be finalized by Friday",
        ]),
        "owner_items": rng.choice(["the technical implementation and testing", "vendor negotiations", "stakeholder communications"]),
        "their_items": rng.choice(["the design review and client approvals", "the financial analysis", "the security review"]),
        "next_meeting": rng.choice(["next Tuesday", "in two weeks", "end of the month", "after we have initial results"]),
        "meeting_type": rng.choice(["sync", "one-on-one", "team standup", "review meeting", "planning session"]),
        "original_time": rng.choice(["Tuesday at 10am", "Wednesday 2pm", "Thursday morning"]),
        "new_time": rng.choice(["Wednesday at 11am", "Thursday 3pm", "Friday at 10am"]),
        "deliverable": rng.choice(["proposal", "report", "deck", "analysis", "wireframes", "spec document", "budget"]),
        "quality": rng.choice(["solid", "good", "strong with a few gaps", "promising but needs work"]),
        "thought_1": rng.choice([
            "the executive summary could be tighter",
            "I'd reorder sections 3 and 4",
            "the data in the appendix doesn't match the summary",
            "the competitive section needs more specifics",
        ]),
        "thought_2": rng.choice([
            "the timeline feels aggressive given our current bandwidth",
            "I think we should add a risk section",
            "the pricing analysis is compelling",
        ]),
        "thought_3": rng.choice([
            "Overall though, really nice work.",
            "Happy to help polish the final version.",
            "Let's aim to finalize by end of week.",
            "",
        ]),
        "strength": rng.choice([
            "how clearly you laid out the business case",
            "the depth of the competitive analysis",
            "the clean structure and tight writing",
        ]),
        "improvement": rng.choice([
            "the ROI section — I think we can make a stronger case with real numbers",
            "the implementation timeline — it reads as best-case, not realistic-case",
            "the executive summary — it buries the lead",
        ]),
        "additional": rng.choice([
            "I'm available to discuss if you want to talk it through.",
            "This is solid work.",
            "",
        ]),
        "concern_1": rng.choice([
            "the cost projections seem optimistic",
            "we're missing the competitive angle entirely",
            "the legal language in section 3 isn't accurate",
        ]),
        "concern_2": rng.choice([
            "the timeline doesn't account for the holiday freeze",
            "the target market definition is too broad",
            "I don't think we've addressed the main objection",
        ]),
        "recommendation": rng.choice(["revise the financial model", "get legal to review", "add the missing data points", "narrow the scope"]),
        "change_1": rng.choice(["Fix the typo on page 3", "Update the date in the header", "Swap the chart on slide 7"]),
        "change_2": rng.choice(["add the disclaimer footer", "round the percentages", "remove the draft watermark"]),
        "recipient": rng.choice(["the client", "the board", "the steering committee", "the executive team"]),
        "event": rng.choice(["offsite", "quarterly review", "launch event", "training session", "team dinner"]),
        "date": rng.choice(["March 15th", "next Thursday", "the 22nd", "December 3rd", "February 8th"]),
        "location": rng.choice(["the downtown office", "the Marriott on 5th", "Conference Room B", "the Austin office"]),
        "attendee_count": str(rng.randint(5, 50)),
        "logistics_detail": rng.choice([
            "Lunch will be provided.",
            "Parking validation is available at the front desk.",
            "We'll send the agenda next week.",
            "Remote dial-in will be available for anyone who can't make it in person.",
        ]),
        "document": rng.choice(["contract", "SOW", "NDA", "invoice", "presentation", "spreadsheet"]),
        "purpose": rng.choice(["the board packet", "our audit file", "the client presentation", "the quarterly review"]),
        "deadline": rng.choice(["end of day Friday", "Tuesday at noon", "next Monday", "before the meeting"]),
        "alternative": rng.choice([
            "I can try to pull it from the shared drive",
            "let me know and I'll reconstruct it from my notes",
            "just let me know and I'll check with the team",
        ]),
        "task": rng.choice(["the expense report", "the performance review", "the compliance training", "the project update"]),
        "due_date": rng.choice(["this Friday", "end of day tomorrow", "next Monday", "by close of business Thursday"]),
        "dates": rng.choice(["next week Monday through Wednesday", "December 20-31", "Thursday and Friday", "the first two weeks of January"]),
        "coverage_person": rng.choice(["Sarah", "Mike", "Jordan", "Alex"]),
        "backup": rng.choice(["them directly", "the team channel", "the on-call rotation"]),
        "period": rng.choice(["Q3", "October", "year-to-date", "H1"]),
        "revenue": rng.choice(["$4.2M", "$1.8M", "$12.6M", "$890K"]),
        "variance": rng.choice(["3% above", "2% below", "right in line with", "5% above"]),
        "driver": rng.choice(["the enterprise segment", "the new product launch", "expansion revenue", "a large one-time deal"]),
        "expense_note": rng.choice([
            "we came in 4% under budget due to delayed hiring",
            "marketing spend was higher than planned but within tolerance",
            "OpEx is tracking to plan",
        ]),
        "planning_item": rng.choice(["next year's budget", "the hiring plan", "the expansion timeline"]),
        "amount": rng.choice(["$15,000", "$8,500", "$42,000", "$3,200"]),
        "item": rng.choice(["new laptops for the engineering team", "the conference sponsorship", "additional cloud infrastructure", "the marketing automation platform"]),
        "budget_line": rng.choice(["IT capital", "marketing", "professional development", "operations"]),
        "vendor": rng.choice(["Dell", "the agency", "AWS", "the consulting firm"]),
        "lead_time": rng.choice(["2-3 weeks", "5 business days", "30 days", "immediate"]),
        "budget_status": rng.choice(["running about 5% over", "tracking to plan", "slightly under budget", "in good shape"]),
        "variance_source": rng.choice(["the unplanned hire in September", "higher-than-expected cloud costs", "the delayed project kickoff"]),
        "explanation": rng.choice([
            "was a conscious decision to accelerate the roadmap",
            "should normalize by end of quarter",
            "we expected and budgeted a contingency for",
        ]),
        "person": rng.choice(NAMES),
        "role": rng.choice(["Senior Engineer", "Product Manager", "Marketing Director", "Account Executive", "Operations Lead"]),
        "compensation": rng.choice(["$135K base + 15% bonus + standard equity", "$95K base with quarterly bonuses", "$160K total comp"]),
        "priorities": rng.choice([
            "handing off the active client accounts and documenting the build process",
            "knowledge transfer on the analytics platform and vendor relationships",
            "completing the in-flight projects and transitioning ongoing work",
        ]),
        "actions_taken": rng.choice([
            "specific examples and put together a performance improvement plan",
            "the feedback from the 360 review and set clear expectations",
        ]),
        "metrics": rng.choice([
            "project completion rate and stakeholder satisfaction",
            "response time and quality scores",
            "quota attainment and pipeline generation",
        ]),
        "share_item": rng.choice([
            "an article about the shift to AI-first security",
            "a podcast episode with the CEO of our biggest competitor",
            "a case study from a company doing exactly what we're planning",
        ]),
        "angle": rng.choice([
            "how it might affect our positioning",
            "whether we should adjust our approach",
            "the implications for our product roadmap",
        ]),
        "answer": rng.choice([
            "yes, I think we should go ahead with the plan as discussed",
            "I'd recommend we wait until after the quarterly review",
            "the short answer is no, but there's nuance worth discussing",
        ]),
        "question": rng.choice([
            "anyone at the company who has experience with SOC 2 audits",
            "if there's a preferred vendor for office furniture",
            "who owns the relationship with the industry association",
        ]),
        "formal_topic": rng.choice([
            "effective immediately, the company will implement a revised travel policy",
            "the Board of Directors has approved the proposed restructuring plan",
            "we have completed our review of the compliance framework",
        ]),
        "obligation": rng.choice([
            "all parties are expected to adhere to the revised terms",
            "the deliverables outlined in Appendix A remain in effect",
        ]),
        "document_type": rng.choice(["Master Services Agreement", "Statement of Work", "Non-Disclosure Agreement", "Employment Agreement"]),
        "reviewer": rng.choice(["our legal counsel", "the compliance team", "outside counsel"]),
        "organization": rng.choice(["the executive leadership team", "the Board of Directors", "the management committee"]),
        "factors": rng.choice(["market conditions, internal capabilities, and stakeholder feedback", "all available data and expert recommendations"]),
        "interests": rng.choice(["all stakeholders", "the long-term health of the organization", "our employees and clients"]),
        "commitment": rng.choice(["ensuring a smooth transition", "full transparency throughout the process", "providing regular updates"]),
        "confirmation": rng.choice([
            "the matter has been resolved as of the date referenced in your correspondence",
            "all requirements have been met and the account is in good standing",
        ]),
        "name": rng.choice(NAMES),
        "sender": rng.choice(SENDERS),
        "metric_1": rng.choice(["p99 latency at 45ms", "error rate at 0.02%", "throughput at 2400 req/s"]),
        "metric_2": rng.choice(["CPU utilization at 38%", "memory steady at 2.1GB", "queue depth at zero"]),
        "caveat": rng.choice([
            "the cache hit ratio dropped slightly during the rollout window",
            "we saw a brief spike in 5xx errors during the cutover that self-resolved",
            "the new indexing job is taking longer than expected on the first run",
        ]),
        "issue": rng.choice(["checkout flow", "notification delivery", "search ranking", "data sync"]),
        "root_cause": rng.choice([
            "a race condition in the connection pool under high concurrency",
            "an off-by-one error in the pagination logic",
            "a missing null check on the response handler",
        ]),
        "fix_description": rng.choice([
            "a three-line change in the middleware plus a regression test",
            "refactoring the retry logic to use exponential backoff",
            "adding input validation at the API boundary",
        ]),
        "test_cases": rng.choice(["the full regression suite plus the edge cases from the bug report", "all existing tests plus 4 new ones targeting the specific failure mode"]),
        "feature": rng.choice(["real-time notifications", "the multi-tenant data layer", "the new reporting engine", "SSO integration"]),
        "approach_1": rng.choice(["event-driven with a message queue", "polling with a background worker", "WebSockets for real-time push"]),
        "approach_2": rng.choice(["a simpler REST-based approach with client-side polling", "server-sent events", "a managed service like Firebase"]),
        "tradeoffs": rng.choice([
            "complexity versus latency",
            "build time versus operational overhead",
            "flexibility versus simplicity",
        ]),
        "reasoning": rng.choice([
            "it scales better and we'll need that within 6 months",
            "the team has more experience with that stack",
            "the operational burden is significantly lower",
        ]),
        "count": str(rng.randint(3, 15)),
        "critical_count": str(rng.randint(1, 3)),
        "critical_items": rng.choice([
            "an outdated TLS library and an exposed debug endpoint",
            "a SQL injection vector in the search endpoint",
            "a missing CSRF token on the admin panel",
        ]),
    }

    result = template
    for key, value in replacements.items():
        result = result.replace("{" + key + "}", value)
    return result


ALL_TEMPLATE_POOLS = [
    PROJECT_TEMPLATES,
    MEETING_TEMPLATES,
    FEEDBACK_TEMPLATES,
    LOGISTICS_TEMPLATES,
    FINANCIAL_TEMPLATES,
    HR_TEMPLATES,
    CASUAL_TEMPLATES,
    FORMAL_TEMPLATES,
    TECHNICAL_TEMPLATES,
]


def generate_diverse_corpus(size: int = 500, seed: int = 42) -> list[str]:
    """Generate a diverse corpus of email-shaped texts."""
    rng = random.Random(seed)
    texts = []

    for _ in range(size):
        pool = rng.choice(ALL_TEMPLATE_POOLS)
        template = rng.choice(pool)
        body = _fill_template(template, rng)

        # 60% chance of greeting, 60% chance of closer
        if rng.random() < 0.6:
            greeting = rng.choice(GREETINGS)
            body = _fill_template(greeting, rng) + body
        if rng.random() < 0.6:
            closer = rng.choice(CLOSERS)
            body = body + _fill_template(closer, rng)

        # Occasionally duplicate/extend for length variety
        if rng.random() < 0.15:
            extra_pool = rng.choice(ALL_TEMPLATE_POOLS)
            extra = _fill_template(rng.choice(extra_pool), rng)
            body = body + "\n\n" + extra

        texts.append(body.strip())

    return texts


# ---- Main ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Seed the CPA background corpus.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--from-enron", action="store_true",
                      help="Pull from Enron Postgres DB (needs DATABASE_URL)")
    mode.add_argument("--from-file", type=str, default=None,
                      help="Load from a newline-delimited text file")
    mode.add_argument("--generate", action="store_true", default=True,
                      help="Generate diverse synthetic corpus (default)")
    ap.add_argument("--size", type=int, default=500,
                    help="Number of texts to generate (default: 500)")
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed for reproducibility")
    args = ap.parse_args()

    from background_corpus import BackgroundCorpus, build_from_enron

    if args.from_enron:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            log.error("DATABASE_URL not set. Use --generate for synthetic corpus.")
            return 1
        corpus = build_from_enron(database_url, sample_size=args.size)
        if len(corpus) == 0:
            log.error("Built empty corpus from Enron. Is the DB populated?")
            return 1
        corpus.save()
        log.info("Enron corpus saved: %d texts", len(corpus))
        return 0

    if args.from_file:
        path = Path(args.from_file)
        if not path.exists():
            log.error("File not found: %s", path)
            return 1
        raw_texts = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        corpus = BackgroundCorpus()
        corpus.add_raw(raw_texts)
        corpus.save()
        log.info("File corpus saved: %d texts from %s", len(corpus), path)
        return 0

    # Default: generate
    log.info("Generating diverse synthetic corpus (size=%d, seed=%d)", args.size, args.seed)
    raw_texts = generate_diverse_corpus(size=args.size, seed=args.seed)
    corpus = BackgroundCorpus()
    corpus.add_raw(raw_texts)
    corpus.save()
    log.info("Synthetic corpus saved: %d texts (from %d generated)", len(corpus), len(raw_texts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
