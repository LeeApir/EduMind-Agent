"""Acceptance-only global attempt guard; never changes production retry semantics."""

from serve_real_browser import Budget


class GuardedBudget(Budget):
    def reserve(self, kind):
        from app.services.provider_gateway import ProviderError, ProviderErrorCode

        if self.metadata.get("halted"):
            raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING)
        return super().reserve(kind)

    def save(self):
        if any(
            call.get("error_code")
            in {"AUTHENTICATION_FAILED", "RATE_LIMITED", "CAPABILITY_UNAVAILABLE"}
            for call in self.calls
        ):
            self.metadata.setdefault("halted", "AUTH_QUOTA_OR_CAPABILITY")
        super().save()


def install_status_guard(module, budget):
    original = module._check_status

    def checked(response):
        if response.status_code in {401, 402, 403, 429}:
            budget.metadata["halted"] = "AUTH_BALANCE_QUOTA"
            budget.save()
        return original(response)

    module._check_status = checked
