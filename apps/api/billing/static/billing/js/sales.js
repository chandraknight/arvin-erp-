// Initialize the sales page functionality
document.addEventListener('DOMContentLoaded', function() {
    // Get CSRF token for AJAX requests
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    
    const csrftoken = getCookie('csrftoken');
    
    // Update invoice totals in the UI
    function updateInvoiceTotals(data) {
        const subtotalAmount = document.getElementById('subtotal-amount');
        const discountAmount = document.getElementById('discount-amount');
        const taxAmount = document.getElementById('tax-amount');
        const totalAmount = document.getElementById('total-amount');
        
        if (subtotalAmount && data.subtotal !== undefined) {
            subtotalAmount.textContent = 'Rs. ' + parseFloat(data.subtotal).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
        if (discountAmount && data.discount_amount !== undefined) {
            discountAmount.textContent = '- Rs. ' + parseFloat(data.discount_amount).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
        if (taxAmount && data.tax_amount !== undefined) {
            taxAmount.textContent = '+ Rs. ' + parseFloat(data.tax_amount).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
        if (totalAmount && data.total !== undefined) {
            totalAmount.textContent = 'Rs. ' + parseFloat(data.total).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
    }
    
    // Store original values on focus for inputs
    document.addEventListener('focusin', function(e) {
        if (e.target.classList.contains('item-quantity-input')) { // Only for quantity input now
            e.target.setAttribute('data-original-value', e.target.value);
        }
    });
    
    // Enable/disable complete sale button based on items
    const completeSaleBtn = document.getElementById('complete-sale-btn');
    if (completeSaleBtn) {
        // The hasItems variable will be set by the template
        completeSaleBtn.disabled = !window.hasItems;
    }

    // --- Conditional Input Display Logic ---
    const productInputGroup = document.getElementById('product-input-group');
    const packageInputGroup = document.getElementById('package-input-group');
    const descriptionInputGroup = document.getElementById('description-input-group');

    const productSearchInput = document.getElementById('id_product_search');
    const productIdInput = document.getElementById('id_product_id'); // Hidden input: Changed ID
    const priceInput = document.getElementById('id_price');
    const packageSelect = document.getElementById('id_package');
    const descriptionInput = document.getElementById('id_description');
    const descriptionProductSearchInput = document.getElementById('id_description_product_search');
    const descriptionProductIdInput = document.getElementById('id_description_product_id');

    // New function to handle item type switching
    function handleItemTypeSwitch() {
        const selectedType = document.querySelector('input[name="item_type"]:checked').value;

        // Reset inputs for currently INACTIVE groups
        if (selectedType !== 'product') {
            productSearchInput.value = '';
            productIdInput.value = '';
        }
        if (selectedType !== 'package') {
            packageSelect.value = '';
        }
        if (selectedType !== 'description') {
            descriptionInput.value = '';
            descriptionProductSearchInput.value = '';
            descriptionProductIdInput.value = '';
        }
        
        // Clear price only if switching to product or package type, where price is auto-populated
        // For 'description' type, price can be manually entered or set by product search.
        if (selectedType === 'product' || selectedType === 'package') {
            priceInput.value = '';
        }

        // Hide all input groups initially
        productInputGroup.style.display = 'none';
        packageInputGroup.style.display = 'none';
        descriptionInputGroup.style.display = 'none';

        // Show the selected input group
        if (selectedType === 'product') {
            productInputGroup.style.display = 'block';
            productSearchInput.focus();
        } else if (selectedType === 'package') {
            packageInputGroup.style.display = 'block';
            packageSelect.focus();
        } else if (selectedType === 'description') {
            descriptionInputGroup.style.display = 'block';
            descriptionProductSearchInput.focus(); // Focus on search first
        }
    }

    // Add event listener for package selection to update price
    if (packageSelect) {
        packageSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const packagePrice = selectedOption.dataset.packagePrice;
            if (packagePrice) {
                priceInput.value = parseFloat(packagePrice).toFixed(2);
            } else {
                priceInput.value = ''; // Clear if no price or invalid option
            }
        });
    }

    // Attach event listeners to the item type radio buttons
    document.querySelectorAll('input[name="item_type"]').forEach(radio => {
        radio.addEventListener('change', handleItemTypeSwitch);
    });

    // Initial call to set correct state on page load based on default checked radio
    handleItemTypeSwitch();

    // --- Product Typeahead/Autoload & Cart/Add Item Debugging ---

    const productSuggestionsContainer = document.getElementById('product-suggestions');

    // Simple debounce function
    function debounce(func, delay) {
        let timeout;
        return function(...args) {
            const context = this;
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(context, args), delay);
        };
    }

    if (productSearchInput && productSuggestionsContainer) {
        productSearchInput.addEventListener('input', debounce(function() {
            const query = this.value;
            if (query.length < 3) {
                productSuggestionsContainer.innerHTML = '';
                productSuggestionsContainer.classList.add('hidden');
                return;
            }
            fetch(`/products/api/search-products/?term=${query}`)
                .then(response => response.json())
                .then(data => {
                    productSuggestionsContainer.innerHTML = '';
                    if (data.products && data.products.length > 0) {
                        data.products.forEach(product => {
                            const div = document.createElement('div');
                            div.className = 'p-2 cursor-pointer hover:bg-gray-100';
                            div.textContent = product.name;
                            div.dataset.productId = product.id;
                            div.dataset.productPrice = product.price;
                            div.addEventListener('click', function() {
                                productSearchInput.value = this.textContent; // Set input to product name
                                productIdInput.value = this.dataset.productId; // Set hidden product ID
                                priceInput.value = this.dataset.productPrice; // Set price field
                                productSuggestionsContainer.classList.add('hidden');
                                // Removed: handleItemTypeSwitch(); // No longer needed here
                            });
                            productSuggestionsContainer.appendChild(div);
                        });
                        productSuggestionsContainer.classList.remove('hidden');
                    } else {
                        productSuggestionsContainer.classList.add('hidden');
                    }
                })
                .catch(error => {
                    console.error('Error fetching product suggestions:', error);
                    productSuggestionsContainer.classList.add('hidden');
                });
        }, 300));
    }

    // Handle quantity changes (existing logic, ensure it's still working)
    document.querySelectorAll('.item-quantity-input').forEach(input => {
        input.addEventListener('change', function() {
            const itemId = this.dataset.itemId;
            const newQuantity = parseInt(this.value);
            
            if (newQuantity < 1) {
                this.value = 1; // Ensure quantity is at least 1
                return;
            }
            
            fetch(`/billing/api/update-item-quantity/${itemId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ quantity: newQuantity })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const itemTotalSpan = this.closest('[data-item-id]').querySelector('.font-semibold.text-gray-900');
                    if (itemTotalSpan) {
                        itemTotalSpan.textContent = 'Rs. ' + parseFloat(data.item_total).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
                    }
                    updateInvoiceTotals(data); // Update overall totals
                } else {
                    this.value = this.getAttribute('data-original-value') || newQuantity;
                    alert('Failed to update quantity: ' + (data.error || 'Unknown error.'));
                }
            })
            .catch(error => {
                console.error('Error updating item quantity:', error);
                this.value = this.getAttribute('data-original-value') || newQuantity;
                alert('An error occurred while updating the item quantity.');
            });
        });
    });

    // --- Description Product Search Typeahead ---
    const descriptionSuggestionsContainer = document.getElementById('description-suggestions');

    if (descriptionProductSearchInput && descriptionSuggestionsContainer) {
        descriptionProductSearchInput.addEventListener('input', debounce(function() {
            const query = this.value;
            if (query.length < 3) {
                descriptionSuggestionsContainer.innerHTML = '';
                descriptionSuggestionsContainer.classList.add('hidden');
                return;
            }
            fetch(`/products/api/search-products/?term=${query}`)
                .then(response => response.json())
                .then(data => {
                    descriptionSuggestionsContainer.innerHTML = '';
                    if (data.products && data.products.length > 0) {
                        data.products.forEach(product => {
                            const div = document.createElement('div');
                            div.className = 'p-2 cursor-pointer hover:bg-gray-100';
                            div.textContent = ` ${product.name} (Rs. ${parseFloat(product.price).toFixed(2)})`;
                            div.dataset.productId = product.id;
                            div.dataset.productPrice = product.price;
                            div.dataset.productName = product.name;
                            div.addEventListener('click', function() {
                                descriptionProductSearchInput.value = this.dataset.productName; // Set search input to product name
                                descriptionProductIdInput.value = this.dataset.productId; // Set hidden product ID
                                descriptionInput.value = this.dataset.productName; // Set description field
                                priceInput.value = this.dataset.productPrice; // Set price field
                                descriptionSuggestionsContainer.classList.add('hidden');
                                // Removed: handleItemTypeSwitch(); // No longer needed here
                            });
                            descriptionSuggestionsContainer.appendChild(div);
                        });
                        descriptionSuggestionsContainer.classList.remove('hidden');
                    } else {
                        descriptionSuggestionsContainer.classList.add('hidden');
                    }
                })
                .catch(error => {
                    console.error('Error fetching description product suggestions:', error);
                    descriptionSuggestionsContainer.classList.add('hidden');
                });
        }, 300));
    }

    // Clear description product search and id if description input is directly typed into
    if (descriptionInput && descriptionProductSearchInput && descriptionProductIdInput) {
        descriptionInput.addEventListener('input', function() {
            if (this.value.trim() !== '') {
                descriptionProductSearchInput.value = '';
                descriptionProductIdInput.value = '';
            }
        });
    }
});
