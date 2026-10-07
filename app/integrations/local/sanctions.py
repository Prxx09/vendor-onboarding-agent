from hashlib import sha256
from time import perf_counter

from app.integrations.base import VerificationMode, VerificationStatus
from app.integrations.sanctions import SanctionsMatch, SanctionsResult
from app.rules.validation.common import match_score
from app.schemas.domain import SanctionsEntry


class LocalSanctionsProvider:
    provider_name = "local_synthetic_sanctions"

    def __init__(self, entries: list[SanctionsEntry] | None = None):
        self.entries = entries if entries is not None else [
            SanctionsEntry(name="Example Restricted Trading Company", aliases=["ERTC"], list_name="fictional-demo-list")
        ]

    def screen(self, name: str, aliases: list[str], country: str):
        start = perf_counter()
        candidates = [name, *aliases]
        matches = []
        for entry in self.entries:
            all_names = [entry.name, *entry.aliases]
            best = max(((candidate, listed) for candidate in candidates for listed in all_names),
                       key=lambda pair: match_score(pair[0], pair[1]))
            score = match_score(*best)
            if score >= 90:
                matches.append(SanctionsMatch(name=best[1], list_name=entry.list_name, score=score))
        digest = sha256(name.encode()).hexdigest()[:16]
        return SanctionsResult(
            capability="sanctions", provider_name=self.provider_name,
            mode=VerificationMode.LOCAL_SIMULATED,
            status=(VerificationStatus.NOT_CONFIGURED if not self.entries else
                    VerificationStatus.MISMATCH if matches else VerificationStatus.VERIFIED),
            latency_ms=round((perf_counter() - start) * 1000), reference_id=digest,
            matches=matches, details={"simulation": "synthetic_local_list_only"},
        )
