from apps.company.models import Company
from apps.bookkeeping.models import LedgerAccount
from django.db import models
from apps.utils.baseModel import BaseModel
from apps.utils.constant import JOURNAL_ENTRY_TYPES

class Vendor(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='vendors', null=True, blank=True)
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    pan_number = models.CharField(max_length=20, blank=True, null=True, help_text="PAN / VAT registration number")
    ref_by = models.ForeignKey(
        'pos.Referrer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='referred_vendors',
        help_text='Person who referred this vendor.',
    )
    related_ledger_account = models.OneToOneField(
        LedgerAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='vendor_accounts',
        help_text="Automatically assigned ledger account for this vendor's payables."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'name'], name='unique_vendor_name_per_company'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.company is None:
            raise ValueError("Vendor must be associated with a company.")

        # Get or create the parent Accounts Payable account
        accounts_payable_parent, _ = LedgerAccount.objects.get_or_create(
            company=self.company,
            name='Accounts Payable',
            defaults={'account_type': 'LIABILITY'}
        )

        # Create vendor-specific ledger account if it doesn't exist
        if not self.related_ledger_account:
            code = self.generate_vendor_code()
            vendor_account_name = f"Accounts Payable - {self.name} - {code}"
            self.related_ledger_account = LedgerAccount.objects.create(
                company=self.company,
                code=code,
                name=vendor_account_name,
                account_type='LIABILITY',
                parent_account=accounts_payable_parent
            )

        super().save(*args, **kwargs)

        # Create opening balance for the vendor ledger account
        self._create_opening_balance()

    def _create_opening_balance(self):
        """Create opening balance for vendor ledger account if needed"""
        from apps.bookkeeping.models import LedgerOpeningBalance
        from apps.company.models import FiscalYear

        # Get the active fiscal year for the company
        active_fiscal_year = FiscalYear.objects.filter(
            company=self.company,
            is_active=True
        ).first()

        if active_fiscal_year and self.related_ledger_account:
            # Check if opening balance already exists
            existing_balance = LedgerOpeningBalance.objects.filter(
                account=self.related_ledger_account,
                fiscal_year=active_fiscal_year
            ).first()

            if not existing_balance:
                # Create opening balance with zero amount (can be updated later)
                LedgerOpeningBalance.objects.create(
                    account=self.related_ledger_account,
                    fiscal_year=active_fiscal_year,
                    opening_type='CREDIT',  # Payables are typically credit balances
                    amount=0.00  # Default to zero, can be updated later
                )

    def update_opening_balance(self, amount, opening_type='CREDIT', fiscal_year=None):
        """Update opening balance for this vendor's ledger account"""
        from apps.bookkeeping.models import LedgerOpeningBalance
        from apps.company.models import FiscalYear

        if not self.related_ledger_account:
            raise ValueError("Vendor must have a related ledger account")

        # Use provided fiscal year or get active one
        if not fiscal_year:
            fiscal_year = FiscalYear.objects.filter(
                company=self.company,
                is_active=True
            ).first()

        if not fiscal_year:
            raise ValueError("No active fiscal year found for this company")

        # Get or create opening balance record
        opening_balance, created = LedgerOpeningBalance.objects.get_or_create(
            account=self.related_ledger_account,
            fiscal_year=fiscal_year,
            defaults={
                'opening_type': opening_type,
                'amount': amount
            }
        )

        # Update if it already exists
        if not created:
            opening_balance.opening_type = opening_type
            opening_balance.amount = amount
            opening_balance.save()

        return opening_balance

    def get_opening_balance(self, fiscal_year=None):
        """Get opening balance for this vendor's ledger account"""
        from apps.bookkeeping.models import LedgerOpeningBalance
        from apps.company.models import FiscalYear

        if not self.related_ledger_account:
            return None

        # Use provided fiscal year or get active one
        if not fiscal_year:
            fiscal_year = FiscalYear.objects.filter(
                company=self.company,
                is_active=True
            ).first()

        if not fiscal_year:
            return None

        return LedgerOpeningBalance.objects.filter(
            account=self.related_ledger_account,
            fiscal_year=fiscal_year
        ).first()

    @staticmethod
    def generate_vendor_code():
        """Generate a unique vendor code"""
        from random import randint
        return f"VN-{randint(100000, 999999)}"
    
    @classmethod
    def bulk_update_opening_balances(cls, company, opening_balances_data, fiscal_year=None):
        """Bulk update opening balances for multiple vendors
        
        Args:
            company: Company instance
            opening_balances_data: List of dictionaries containing:
                - vendor_id: Vendor ID
                - amount: Opening balance amount
                - opening_type: 'DEBIT' or 'CREDIT'
            fiscal_year: FiscalYear instance (optional, uses active if not provided)
        
        Returns:
            Dictionary with success and error counts
        """
        from apps.bookkeeping.models import LedgerOpeningBalance
        from apps.company.models import FiscalYear
        
        if not fiscal_year:
            fiscal_year = FiscalYear.objects.filter(
                company=company,
                is_active=True
            ).first()
        
        if not fiscal_year:
            raise ValueError("No active fiscal year found for this company")
        
        success_count = 0
        error_count = 0
        errors = []
        
        for data in opening_balances_data:
            try:
                vendor = cls.objects.get(
                    id=data['vendor_id'],
                    company=company
                )
                
                if vendor.related_ledger_account:
                    vendor.update_opening_balance(
                        amount=data['amount'],
                        opening_type=data.get('opening_type', 'CREDIT'),
                        fiscal_year=fiscal_year
                    )
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"Vendor {vendor.name} has no ledger account")
                    
            except cls.DoesNotExist:
                error_count += 1
                errors.append(f"Vendor with ID {data['vendor_id']} not found")
            except Exception as e:
                error_count += 1
                errors.append(f"Error updating vendor {data.get('vendor_id', 'unknown')}: {str(e)}")
        
        return {
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors
        }
