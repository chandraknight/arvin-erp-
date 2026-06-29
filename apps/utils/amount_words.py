from decimal import Decimal

from num2words import num2words


def amount_in_words(amount) -> str:
    """Render a decimal amount as 'One Thousand Two Hundred Rupees Only',
    or 'One Thousand Two Hundred Rupees And Fifty Paisa Only' when there's
    a fractional part — num2words renders a raw decimal as '... Point Five',
    which isn't how currency amounts are normally read out."""
    amount = Decimal(str(amount))
    rupees = int(amount)
    paisa = int((amount - rupees) * 100)

    words = num2words(rupees, lang='en').title() + " Rupees"
    if paisa:
        words += " And " + num2words(paisa, lang='en').title() + " Paisa"
    return words + " Only"
