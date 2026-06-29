# ERP Billing Engine Backend !
This is the backend service for the ERP Billing Engine, built using Django and Django REST Framework. It provides a robust and scalable API to manage billing operations, customer data, invoices, analytics, and other ERP-related functionalities.

## 🚀 Features

- Secure RESTful API for ERP billing operations
- Modular and scalable Django architecture
- Support for customer, product, invoice
- Role-based permissions and authentication
- JSON responses for seamless integration with third-party services
- **Analytics Dashboard**: Fiscal year trends, top customers/products, cash flow, AR aging, vendor stats, and more
- **Export**: Download dashboard analytics as CSV or Excel
- **Search & Filtering**: Paginated lists (invoices, journal entries) support advanced search and filters

## 📊 Analytics & Reporting

- Fiscal year dashboard with sales, expenses, profit trends
- Top N customers/products, vendor stats
- Cash flow and AR aging widgets
- Export dashboard data as CSV or Excel
- All analytics logic is modular and testable

## 🔌 API Endpoints

- All core resources (invoices, customers, products, etc.) via REST API
- **Analytics API**: `/api/analytics/fiscal-year-dashboard/` and related endpoints for trends, top N, cash flow, AR aging, vendor stats
- All analytics endpoints require authentication and support `fiscal_year_id` as a query parameter

## 🧪 Testing

- Unit tests for analytics service functions
- API endpoint tests for all analytics endpoints
- Run tests with:
  ```bash
  python manage.py test
  ```

## 🛠️ Tech Stack

- Backend Framework: Django 5+
- API Framework: Django REST Framework
- Database: PostgreSQL
- Authentication: Token-based / JWT
- Deployment: Docker, Gunicorn, Nginx (optional)

## For Deployment

For detailed Deployment, please refer to [README.DEPLOY.md](README.DEPLOY.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Advanced Inventory Analytics

### Overview
The Advanced Inventory Analytics feature provides comprehensive insights into your inventory management, leveraging predictive analytics and sophisticated data visualization.

### Key Features

#### 1. Inventory Health Overview
- Total product count
- Risk distribution analysis
- Categorization of products into risk levels:
  - High Risk
  - Medium Risk
  - Low Risk

#### 2. Stock Turnover Analysis
Detailed metrics for each product:
- Average Daily Usage
- Current Stock Levels
- Days of Stock Remaining
- Stockout Risk Assessment
- Usage Trend Prediction

#### 3. Predictive Forecasting
Advanced 30-day inventory predictions:
- Exponential Weighted Moving Average
- Historical Average Calculation
- Standard Deviation Analysis

### Visualization
- Interactive Pie Chart for Inventory Risk Distribution
- Color-coded Risk Indicators
- Responsive, Modern UI
- Gradient Design with Intuitive Navigation

### Technical Details
- Uses Linear Regression for Trend Analysis
- Implements Exponential Smoothing
- 180-day Rolling Window for Comprehensive Analysis
- Statistical Calculations with NumPy and SciPy

### Access
Navigate to: `/products/advanced-inventory-analytics/`

### Risk Assessment Criteria
- High Risk: Less than 15 days of stock
- Medium Risk: 15-30 days of stock
- Low Risk: More than 30 days of stock

### Predictive Insights
The feature provides:
- Usage Trend (Increasing/Decreasing/Stable)
- Stock Coverage Ratio
- 30-Day Quantity Prediction

### Recommended Actions
1. Regularly review inventory analytics
2. Pay special attention to high-risk products
3. Use predictive insights for proactive inventory management

### Performance Optimization
- Efficient database queries
- Cached calculations
- Minimal computational overhead