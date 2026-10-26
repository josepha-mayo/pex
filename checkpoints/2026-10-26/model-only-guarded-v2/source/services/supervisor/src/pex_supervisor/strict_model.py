"""Local Strands model adapter: validate SDK stream usage before aggregation.

Not a provider transport or billing gateway. Inner provider retries remain
unqualified. An upstream provider SDK can normalize wire values before this
adapter sees them; this is not raw-wire validation. No external model is
exercised by this feature's local tests.
"""

from strands.models.model import Model

from pex_supervisor import model_only_transport
from pex_supervisor.strict_usage import _usage, validated_sdk_usage


class InvalidModelUsage(ValueError):
    pass


class UsageCheckedModel(Model):
    def __init__(self, model: Model):
        if not model_only_transport.qualified(model):
            raise ValueError("model_only_transport_unqualified")
        if not isinstance(model, Model) or model.stateful:
            raise ValueError("model-only mode requires a stateless Strands Model")
        self.inner = model
        self.receipts: list[tuple[int, int, int]] = []
        self.started = 0
        self.failed = False

    def get_config(self):
        return self.inner.get_config()

    def update_config(self, **kwargs):
        self.inner.update_config(**kwargs)

    async def structured_output(self, *args, **kwargs):
        # The supported SDK emits structured-output tools through stream().
        # Do not authorize an older side channel with unaudited usage.
        raise InvalidModelUsage("unqualified structured-output transport")
        yield  # pragma: no cover - implements the SDK async-generator interface

    async def stream(self, *args, **kwargs):
        if not model_only_transport.qualified(self.inner):
            raise InvalidModelUsage("model_only_transport_unqualified")
        if self.failed:
            raise InvalidModelUsage("prior model call failed; retry refused")
        self.started += 1
        receipt = None
        try:
            async for event in self.inner.stream(*args, **kwargs):
                if "metadata" in event and "usage" in event["metadata"]:
                    raw = _usage(event["metadata"]["usage"])
                    if receipt is not None or raw is None or raw[0] <= 0 or raw[1] <= 0:
                        raise InvalidModelUsage("missing, duplicate or invalid SDK stream usage")
                    receipt = raw
                yield event
            if receipt is None:
                raise InvalidModelUsage("model returned no SDK stream usage receipt")
            self.receipts.append(receipt)
        except BaseException:
            self.failed = True
            raise

    def validated_usage(self, result):
        observed = validated_sdk_usage(result)
        if self.failed or observed is None or self.started != len(self.receipts):
            return None
        expected = (
            len(self.receipts),
            sum(item[0] for item in self.receipts),
            sum(item[1] for item in self.receipts),
        )
        return observed if observed == expected else None
