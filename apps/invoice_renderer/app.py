"""Invoice Renderer: fills a text template with invoice lines. An ordinary function, not AI.

No model, no `verity_ai`, stdlib only. The crawler must score it *none*.
"""

import functools
import os
from decimal import Decimal
from pathlib import Path
from string import Template


def run(event: dict, template: Template) -> dict:
    rows, total = [], Decimal(0)
    for line in event["lines"]:
        amount = Decimal(str(line["quantity"])) * Decimal(str(line["unit_price"]))
        total += amount
        rows.append(
            f"{line['description']}: {line['quantity']} x {line['unit_price']} = {amount:.2f}"
        )
    text = template.substitute(
        invoice_number=event["invoice_number"],
        customer=event["customer"],
        lines="\n".join(rows),
        total=f"{total:.2f}",
    )
    return {"invoice": text}


@functools.cache
def _template() -> Template:
    return Template((Path(__file__).parent / os.environ["INVOICE_TEMPLATE"]).read_text())


def handler(event, context):
    return run(event, _template())
