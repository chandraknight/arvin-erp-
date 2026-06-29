from django.db import models
from apps.bookkeeping.models import LedgerAccount
from apps.customers.services.customer_services import generate_4_digit_code, generate_6_digit_code
from apps.utils.baseModel import BaseModel

class Customer(BaseModel):
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='customers', null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True, unique=True)
    address = models.TextField(max_length=200, blank=True, null=True)
    text = models.TextField(max_length=200, blank=True, null=True)
    pan_number = models.CharField(
        max_length=20, blank=True, null=True,
        help_text='PAN number for VAT/e-billing (buyer_pan in CBMS).'
    )
    ref_by = models.ForeignKey(
        'pos.Referrer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='referred_customers',
        help_text='Person who referred this customer.',
    )
    related_ledger_account = models.OneToOneField(
        LedgerAccount, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='customer_accounts',
        help_text="Automatically assigned ledger account for this customer's receivables."
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.company is None:
            raise ValueError("Customer must be associated with a company.")

        # Get or create the parent Accounts Receivable account
        accounts_receivable_parent, _ = LedgerAccount.objects.get_or_create(
            company=self.company,
            name='Accounts Receivable',
            defaults={'account_type': 'ASSET'}
        )

        # Create customer-specific ledger account if it doesn't exist
        if not self.related_ledger_account:
            code = generate_6_digit_code()
            customer_account_name = f"Accounts Receivable - {self.name} - {code}"
            self.related_ledger_account = LedgerAccount.objects.create(
                company=self.company,
                code=code,
                name=customer_account_name,
                account_type='ASSET',
                parent_account=accounts_receivable_parent
            )

        super().save(*args, **kwargs)
        
        # Create opening balance for the customer ledger account
        self._create_opening_balance()
    
    def _create_opening_balance(self):
        """Create opening balance for customer ledger account if needed"""
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
                    opening_type='DEBIT',  # Receivables are typically debit balances
                    amount=0.00  # Default to zero, can be updated later
                )
    
    def update_opening_balance(self, amount, opening_type='DEBIT', fiscal_year=None):
        """Update opening balance for this customer's ledger account"""
        from apps.bookkeeping.models import LedgerOpeningBalance
        from apps.company.models import FiscalYear
        
        if not self.related_ledger_account:
            raise ValueError("Customer must have a related ledger account")
        
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
        """Get opening balance for this customer's ledger account"""
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
    
    @classmethod
    def bulk_update_opening_balances(cls, company, opening_balances_data, fiscal_year=None):
        """Bulk update opening balances for multiple customers
        
        Args:
            company: Company instance
            opening_balances_data: List of dictionaries containing:
                - customer_id: Customer ID
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
                customer = cls.objects.get(
                    id=data['customer_id'],
                    company=company
                )
                
                if customer.related_ledger_account:
                    customer.update_opening_balance(
                        amount=data['amount'],
                        opening_type=data.get('opening_type', 'DEBIT'),
                        fiscal_year=fiscal_year
                    )
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f"Customer {customer.name} has no ledger account")
                    
            except cls.DoesNotExist:
                error_count += 1
                errors.append(f"Customer with ID {data['customer_id']} not found")
            except Exception as e:
                error_count += 1
                errors.append(f"Error updating customer {data.get('customer_id', 'unknown')}: {str(e)}")
        
        return {
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors
        }
