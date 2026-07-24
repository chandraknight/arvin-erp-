class SalesHandler {
    constructor() {
        this.csrfToken = this.getCookie('csrftoken');
        this.invoiceId = document.querySelector('#invoice-id')?.value;
        this.cache = {};
        this.timeouts = {}; // Store timeouts for debouncing
        this.init();
    }

    init() {
        this.cacheElements();
        this.setupEventListeners();
        this.initializeProductSearch();
    }

    cacheElements() {
        this.cache = {
            invoiceForm: document.getElementById('invoice-update-form'),
            printButton: document.querySelector('[data-js-print]'),
            productSearch: document.getElementById('id_product_search'),
            productIdInput: document.getElementById('id_product'),
            quantityInput: document.getElementById('id_quantity'),
            priceInput: document.getElementById('id_price'),
            suggestionsContainer: document.getElementById('product-suggestions'),
            discountInput: document.getElementById('id_discount_percent'),
            taxInput: document.getElementById('id_tax_percent'),
            invoiceTotal: document.getElementById('invoice-total')
        };
    }

    setupEventListeners() {
        // Event delegation for dynamic content
        document.body.addEventListener('input', this.handleInput.bind(this));
        document.body.addEventListener('submit', this.handleFormSubmit.bind(this));
        document.body.addEventListener('click', this.handleClick.bind(this));
        document.addEventListener('focusin', this.handleFocusIn.bind(this));

        // Print button
        if (this.cache.printButton) {
            this.cache.printButton.addEventListener('click', this.handlePrint.bind(this));
        }

        // Initialize quantity inputs
        document.querySelectorAll('.item-quantity-input').forEach(input => {
            input.dataset.originalValue = input.value;
        });

        // Initialize discount and tax inputs
        if (this.cache.discountInput) {
            this.setupPercentageInput('discount');
        }
        if (this.cache.taxInput) {
            this.setupPercentageInput('tax');
        }
    }

    handleInput(e) {
        const target = e.target;
        if (target.classList.contains('item-quantity-input')) {
            this.debounce(() => this.handleQuantityChange(target), 300);
        }
    }

    handleClick(e) {
        // Handle remove buttons
        const removeBtn = e.target.closest('[data-js-remove-item]');
        if (removeBtn) {
            e.preventDefault();
            this.handleRemoveItem(removeBtn);
        }
        
        // Handle clicks outside product search
        if (this.cache.suggestionsContainer && 
            !this.cache.productSearch.contains(e.target) && 
            !this.cache.suggestionsContainer.contains(e.target)) {
            this.cache.suggestionsContainer.classList.add('hidden');
        }
    }
    
    handleFocusIn(e) {
        // Store original values on focus
        if (e.target.classList.contains('item-quantity-input') || 
            e.target.id === 'id_discount_percent' || 
            e.target.id === 'id_tax_percent') {
            e.target.dataset.originalValue = e.target.value;
        }
    }

    async handleQuantityChange(input) {
        const itemId = input.dataset.itemId;
        const newQuantity = parseInt(input.value);
        const originalValue = input.dataset.originalValue || '1';
        
        // Basic validation
        if (isNaN(newQuantity) || newQuantity < 1) {
            input.value = originalValue;
            return;
        }

        // Show loading state
        input.disabled = true;
        const itemRow = input.closest('tr');
        const subtotalElement = itemRow?.querySelector('.item-subtotal');
        
        if (subtotalElement) {
            subtotalElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }

        try {
            const response = await fetch(`/billing/api/update-item-quantity/${itemId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ quantity: newQuantity })
            });

            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            if (data.success) {
                // Update the UI with new values
                if (subtotalElement) {
                    subtotalElement.textContent = `Rs. ${data.item.total.toFixed(2)}`;
                }
                
                // Update the input value and original value
                input.value = data.item.quantity;
                input.dataset.originalValue = data.item.quantity;
                
                // Trigger any total updates
                if (data.invoice) {
                    this.updateInvoiceTotals(data.invoice);
                }
                
                this.showFeedback('success', 'Quantity updated');
            } else {
                throw new Error(data.error || 'Failed to update quantity');
            }
        } catch (error) {
            console.error('Error updating quantity:', error);
            input.value = originalValue;
            this.showFeedback('error', error.message || 'Failed to update quantity');
        } finally {
            input.disabled = false;
        }
    }

    async handleFormSubmit(e) {
        const form = e.target.closest('form');
        if (!form) return;

        e.preventDefault();
        const submitButton = form.querySelector('button[type="submit"]');
        this.setLoading(submitButton, true);

        try {
            const formData = new FormData(form);
            const response = await fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });

            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            if (data.redirect_url) {
                window.location.href = data.redirect_url;
            } else {
                window.location.reload();
            }
        } catch (error) {
            console.error('Error submitting form:', error);
            this.showFeedback('error', 'Failed to save changes');
        } finally {
            this.setLoading(submitButton, false);
        }
    }

    handlePrint(e) {
        if (e) e.preventDefault();
        const originalTitle = document.title;
        document.title = `Invoice-${document.querySelector('[name="invoice_number"]')?.value || 'DRAFT'}`;
        window.print();
        setTimeout(() => {
            document.title = originalTitle;
        }, 1000);
    }

    async handleRemoveItem(button) {
        if (!confirm('Are you sure you want to remove this item?')) {
            return;
        }
        
        const itemRow = button.closest('tr');
        if (!itemRow) return;
        
        // Show loading state
        const originalHtml = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.classList.add('opacity-50');
        
        try {
            const url = button.href || button.dataset.url;
            if (!url) throw new Error('No URL specified for removal');
            
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.csrfToken
                }
            });
            
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            if (data.success) {
                // If we have updated totals, update the UI
                if (data.invoice) {
                    this.updateInvoiceTotals(data.invoice);
                }
                
                // Remove the row with animation
                itemRow.style.opacity = '0';
                setTimeout(() => {
                    itemRow.remove();
                    this.showFeedback('success', 'Item removed');
                }, 300);
                
                // Trigger HTMX update if available
                if (typeof htmx !== 'undefined') {
                    htmx.trigger('#invoice-totals', 'updateTotals', data);
                }
            } else {
                throw new Error(data.error || 'Failed to remove item');
            }
        } catch (error) {
            console.error('Error removing item:', error);
            button.innerHTML = originalHtml;
            button.classList.remove('opacity-50');
            this.showFeedback('error', error.message || 'Failed to remove item');
        }
    }

    // Utility methods
    debounce(key, func, wait) {
        clearTimeout(this.timeouts[key]);
        this.timeouts[key] = setTimeout(() => {
            func();
        }, wait);
    }
    
    setupPercentageInput(type) {
        const input = this.cache[`${type}Input`];
        const endpoint = `/billing/api/update-${type}/${this.invoiceId}/`;
        const fieldName = `${type}_percent`;
        
        input.addEventListener('input', () => {
            const value = parseFloat(input.value) || 0;
            const originalValue = input.dataset.originalValue || '0';
            
            // Basic validation
            if (isNaN(value) || value < 0 || value > 100) {
                input.value = originalValue;
                return;
            }
            
            this.debounce(
                `${type}-update`,
                () => this.updatePercentage(endpoint, fieldName, input, value),
                500
            );
        });
    }
    
    async updatePercentage(endpoint, fieldName, input, value) {
        input.disabled = true;
        
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ [fieldName]: value })
            });
            
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            if (data.success) {
                this.updateInvoiceTotals(data);
                input.dataset.originalValue = input.value;
                this.showFeedback('success', `${fieldName.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')} updated`);
            }
        } catch (error) {
            console.error(`Error updating ${fieldName}:`, error);
            input.value = input.dataset.originalValue || '0';
            this.showFeedback('error', `Failed to update ${fieldName}`);
        } finally {
            input.disabled = false;
        }
    }
    
    updateInvoiceTotals(data) {
        // Update any UI elements that display totals
        if (data.discount_amount !== undefined) {
            const discountEl = document.getElementById('discount-amount');
            if (discountEl) discountEl.textContent = data.discount_amount.toFixed(2);
        }
        if (data.tax_amount !== undefined) {
            const taxEl = document.getElementById('tax-amount');
            if (taxEl) taxEl.textContent = data.tax_amount.toFixed(2);
        }
        if (data.total !== undefined) {
            const totalEl = document.getElementById('total-amount') || this.cache.invoiceTotal;
            if (totalEl) totalEl.textContent = data.total.toFixed(2);
        }
    }

    setLoading(element, isLoading) {
        if (!element) return;
        
        if (isLoading) {
            element.disabled = true;
            const originalHTML = element.innerHTML;
            element.dataset.originalHtml = originalHTML;
            element.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
        } else {
            element.disabled = false;
            if (element.dataset.originalHtml) {
                element.innerHTML = element.dataset.originalHtml;
                delete element.dataset.originalHtml;
            }
        }
    }

    initializeProductSearch() {
        const { productSearch, productIdInput, priceInput, suggestionsContainer } = this.cache;
        if (!productSearch || !suggestionsContainer) return;
        
        productSearch.addEventListener('input', () => {
            const query = productSearch.value.trim();
            if (query.length < 2) {
                suggestionsContainer.classList.add('hidden');
                return;
            }
            
            this.debounce(
                'product-search',
                () => this.searchProducts(query),
                300
            );
        });
        
        // Clear product ID when search is cleared
        productSearch.addEventListener('input', () => {
            if (!productSearch.value) {
                if (productIdInput) productIdInput.value = '';
                suggestionsContainer.classList.add('hidden');
            }
        });
    }
    
    async searchProducts(query) {
        const { suggestionsContainer, productSearch, productIdInput, priceInput } = this.cache;
        
        try {
            const response = await fetch(`/products/search-items/?term=${encodeURIComponent(query)}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': this.csrfToken
                }
            });
            
            if (!response.ok) throw new Error('Network response was not ok');
            
            const data = await response.json();
            suggestionsContainer.innerHTML = '';
            
            if (data.length > 0) {
                data.forEach(item => {
                    const suggestion = document.createElement('div');
                    suggestion.className = 'p-2 cursor-pointer hover:bg-gray-200 text-sm text-gray-800';
                    suggestion.textContent = item.label;
                    
                    if (item.id) {
                        suggestion.dataset.productId = item.id;
                        if (item.price) suggestion.dataset.productPrice = item.price;
                        
                        suggestion.addEventListener('click', () => {
                            productSearch.value = item.label.split(' (')[0];
                            if (productIdInput) productIdInput.value = item.id;
                            if (priceInput && !priceInput.value && item.price) {
                                priceInput.value = item.price;
                            }
                            suggestionsContainer.classList.add('hidden');
                        });
                        
                        suggestionsContainer.appendChild(suggestion);
                    }
                });
                suggestionsContainer.classList.remove('hidden');
            } else {
                suggestionsContainer.classList.add('hidden');
            }
        } catch (error) {
            console.error('Error searching products:', error);
            suggestionsContainer.classList.add('hidden');
        }
    }
    
    showFeedback(type, message) {
        // Remove any existing feedback
        const existingFeedback = document.querySelector('.feedback-message');
        if (existingFeedback) existingFeedback.remove();

        const feedback = document.createElement('div');
        feedback.className = `feedback-message fixed top-4 right-4 p-4 rounded shadow-lg z-50 ${
            type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
        }`;
        feedback.textContent = message;
        document.body.appendChild(feedback);
        
        // Auto-remove after 3 seconds
        setTimeout(() => {
            feedback.classList.add('opacity-0', 'transition-opacity', 'duration-500');
            setTimeout(() => feedback.remove(), 500);
        }, 3000);
    }

    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.salesHandler = new SalesHandler();
});
