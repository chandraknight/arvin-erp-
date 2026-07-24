from datetime import date

from django.test import TestCase

from apps.company.models import Company, FiscalYear


class FiscalYearCloseNextYearSpanTests(TestCase):
    """
    Regression test for a bug where close() derived the next fiscal year's
    BS end date by copying the previous FY's AD day-count. Because BS year
    lengths vary (365/366 days), that drifted the auto-created FY off the
    Shrawan 1 -> Ashad end boundary after a few consecutive closes.
    """

    def setUp(self):
        self.company = Company.objects.create(name="Close Test Co")

    def test_repeated_close_keeps_shrawan_ashad_alignment(self):
        fy = FiscalYear.objects.create(
            company=self.company,
            start_date=date(2020, 7, 17),
            end_date=date(2021, 7, 15),
            start_date_bs="2077-04-01",
            end_date_bs="2078-03-31",
            is_active=True,
        )
        for _ in range(4):
            fy.close(closed_by_user=None)
            next_fy = FiscalYear.objects.filter(
                company=self.company, start_date__gt=fy.start_date,
            ).order_by('start_date').last()
            self.assertEqual(int(next_fy.start_date_bs.split('-')[1]), 4)
            self.assertEqual(int(next_fy.end_date_bs.split('-')[1]), 3)
            fy = next_fy
