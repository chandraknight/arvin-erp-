from django.core.management.base import BaseCommand
from apps.products.models import Category, CategoryType, Product
from apps.company.models import Company
from apps.ecom.models import SiteSettings
from django.db.models import Q

class Command(BaseCommand):
    help = 'Sync categories, site settings, and map existing products for dpsdabu.com'

    def handle(self, *args, **options):
        company = Company.objects.first()
        if not company:
            self.stdout.write(self.style.ERROR('No company found in the database.'))
            return

        self.stdout.write(f'Syncing for company: {company.name}')

        # 1. Update Site Settings
        settings, created = SiteSettings.objects.get_or_create(company=company)
        settings.store_name = "D.P.S Trade Dabu"
        settings.tagline = "Quality Products from DPS Building, Kalanki"
        settings.contact_email = "dpsdabu@gmail.com"
        settings.contact_address = "DPS Building, Kalanki, Near Kalanki Malpot, Kathmandu"
        settings.save()
        self.stdout.write(self.style.SUCCESS(f'Updated SiteSettings for {company.name}'))

        # 2. Ensure a default CategoryType exists
        category_type, created = CategoryType.objects.get_or_create(
            company=company,
            name='General',
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created CategoryType: {category_type.name}'))

        # 3. Sync Categories
        dps_categories = [
            "Antique & Decor",
            "Electronics & Electricals",
            "Gold-plated",
            "Household Essentials",
            "Jewellery",
            "Kitchen & Toilet Items",
            "Lifestyle",
            "Silver"
        ]

        category_objs = {}
        for cat_name in dps_categories:
            category, created = Category.objects.get_or_create(
                company=company,
                name=cat_name,
                defaults={
                    'type': category_type,
                }
            )
            category_objs[cat_name] = category
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created Category: {cat_name}'))
            else:
                if not category.type:
                    category.type = category_type
                    category.save()
                self.stdout.write(f'Category already exists: {cat_name}')

        # 4. Tie up existing products
        self.stdout.write('Mapping existing products to new categories...')
        
        mappings = {
            "Kitchen & Toilet Items": [
                'kitchen', 'faucet', 'tap', 'chopper', 'yogurt maker', 'curd maker', 'dahi maker', 
                'soap dispenser', 'oil dispenser', 'vegetable peeler', 'cutter', 'knife', 'slicer', 
                'ice tray', 'cup cake', 'toothbrush holder', 'bath', 'shower', 'urinal cubes', 
                'sani cubes', 'odonil', 'dish', 'bowl', 'spoon', 'fork', 'napkins', 'toilet paper', 
                'facial tissue', 'egg holder', 'drain clean', 'mug', 'grater', 'planer', 'peeler',
                'pot holder', 'coaster', 'napkin', 'cup holder', 'pouch sealer', 'sealing clip'
            ],
            "Electronics & Electricals": [
                'electric', 'shoe heat dryer', '150 watt', 'lamp', 'led', 'bulb', 'battery', 
                'charger', 'fan', 'heater', 'socket', 'plug', 'electronic'
            ],
            "Household Essentials": [
                'laundry beads', 'laundry detergent', 'storage', 'rainbow multi storage', 'wall holder', 
                'hook', 'shoe shine', 'cloth hanging clip', 'steel wool', 'washing machine cleaner', 
                'anti shock pad', 'window cleaning brush', 'cloth clips', 'tape', 'pliers', 'cleaner',
                'scale gone', 'wind noise reduction', 'under door blocker'
            ],
            "Lifestyle": [
                'car trash can', 'auto organizer', 'sticky roller', 'lint roller', 'travel', 
                'pocket tissue', 'drying rope', 'scrub glove', 'ice roller', 'exfoliator', 
                'face and neck', 'makeup', 'gym', 'fitness', 'yoga'
            ],
            "Jewellery": [
                'ear-ring', 'ring', 'necklace', 'bracelet', 'jewelry', 'ear ring', 'earrings'
            ],
            "Gold-plated": [
                'gold plated', 'gold-plated'
            ],
            "Silver": [
                'silver'
            ],
            "Antique & Decor": [
                'antique', 'decor', 'vase', 'painting', 'statue', 'ornament'
            ]
        }

        total_mapped = 0
        products = Product.objects.filter(company=company)
        
        for cat_name, keywords in mappings.items():
            category = category_objs[cat_name]
            q_objects = Q()
            for kw in keywords:
                q_objects |= Q(name__icontains=kw) | Q(ecom_description__icontains=kw)
            
            # Update products that match keywords and are not already in a more specific category
            # (If they are currently in 'Imported' or 'None' or have no specific mapping yet)
            updated_count = products.filter(q_objects).update(category=category)
            if updated_count > 0:
                self.stdout.write(self.style.SUCCESS(f'Mapped {updated_count} products to {cat_name}'))
                total_mapped += updated_count

        self.stdout.write(self.style.SUCCESS(f'Successfully synced categories, settings and mapped {total_mapped} products.'))
