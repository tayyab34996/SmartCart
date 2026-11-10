# SmartCart: Data Cleaning, Exploratory Analysis & Preprocessing Pipeline

Conversational grocery basket planning with semantic search, repeat-purchase prediction, and constraint-aware recommendation.

---

## 1. Problem Statement

Modern grocery shopping involves repeated purchases of routine household staples, exploratory discovery of novel ingredients, and strict household constraints (budget limits, dietary restrictions, and meal recipe fulfillment). Traditional recommendation systems frequently treat all grocery items as independent one-off purchases, failing to model:
1. **Repeat Purchase Dynamics**: Whether a consumer will reorder a previously purchased staple or purchase an exploratory item.
2. **Temporal Cadence**: Weekly, bi-weekly, and monthly replenishment cycles.
3. **Cart Assembly Mechanics**: The sequence in which users construct baskets (staples entered first versus impulse/exploratory items added late).
4. **Relational Constraints**: Harmonizing transactional purchase histories (Instacart) with culinary recipe fulfillment (Food.com).

This repository implements the complete end-to-end data science foundation for SmartCart: rigorous data cleaning, exhaustive exploratory data analysis (EDA), behavioral insight extraction, and feature scaling/normalization.

---

## 2. Dataset Details & Download Links

The project utilizes the **Instacart Market Basket Analysis** dataset as its primary transactional foundation, augmented with culinary data from **Food.com Recipes**:

| Dataset | Source Provider | Scope & Size | Key Tables / Files | Download Link |
| :--- | :--- | :--- | :--- | :--- |
| **Instacart Market Basket** | Instacart (Kaggle) | 3.4M+ orders, 206K+ users, 49.7K products, 33.8M item interactions | `orders.csv`, `products.csv`, `order_products__train.csv`, `order_products__prior.csv`, `aisles.csv`, `departments.csv` | [Kaggle Competition](https://www.kaggle.com/c/instacart-market-basket-analysis/data) |
| **Food.com Recipes** | Food.com / Kaggle | 522,517 recipes, 1.4M reviews | `recipes.csv`, `recipes.parquet`, `reviews.csv` | [Kaggle Food.com](https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews) |

> **Note on Data Storage**: Large raw archives (`data/raw/archive_3.zip` and `archive_4.zip`) are tracked via `.gitignore` to maintain a lightweight repository. Cleaned and scaled data subsets are versioned in `data/processed/`, and reproducible generation scripts stream directly from local archives.

### Target Variable & Feature Schema

- **Target Variable**: `reordered` (Binary flag: `1` if the product was reordered in this transaction by the customer; `0` if first-time trial).
- **Core Features**:
  - `order_id`: Unique identifier for each checkout transaction.
  - `user_id`: Customer identifier enabling longitudinal purchase profiling.
  - `order_number`: Customer-specific chronological sequence order rank ($1, 2, \dots, 100$).
  - `order_dow`: Day of week the order was placed ($0 = \text{Sunday}, 1 = \text{Monday}, \dots, 6 = \text{Saturday}$).
  - `order_hour_of_day`: Hour of order placement ($0 \dots 23$).
  - `days_since_prior_order`: Interval in days elapsed since customer's previous order ($0 \dots 30$).
  - `product_id`, `product_name`: SKU identifier and standardized name.
  - `aisle_id`, `aisle`: Product category subdivision (134 categories).
  - `department_id`, `department`: Top-level grocery category (21 departments).
  - `add_to_cart_order`: Ordinal sequence position in which the item entered the digital basket.
- **Engineered Preprocessed Features**:
  - `is_first_order`: Binary flag indicating missingness in prior order interval (`order_number == 1`).
  - `order_dow_sin`, `order_dow_cos`: Continuous cyclical sine/cosine transformations of day-of-week.
  - `order_hour_sin`, `order_hour_cos`: Continuous cyclical sine/cosine transformations of hour-of-day.
  - `cart_ratio`: Normalized cart position relative to total basket item count ($\frac{\text{add\_to\_cart\_order}}{\text{basket\_size}}$).

---

## 3. Data Cleaning Pipeline Summary

The data cleaning pipeline is implemented and fully executed in [`notebooks/01_data_cleaning.ipynb`](notebooks/01_data_cleaning.ipynb):

1. **Relational Multi-Table Ingestion**: Streamed and joined 100,000 evaluation order-product transactions with full order metadata, products, aisles, and departments.
2. **Missing Value Resolution**:
   - `days_since_prior_order` contained missing values exclusively corresponding to initial customer transactions (`order_number == 1`).
   - Rather than dropping rows (which would introduce customer survival bias), missing values were imputed with `0`, and an explicit binary indicator `is_first_order` was created to preserve structural signal.
3. **Duplicate Detection & Deduplication**:
   - Evaluated composite uniqueness on `(order_id, product_id)`.
   - Verified zero conflicting duplicate line items within individual orders.
4. **Outlier Detection & Capping (IQR Rule)**:
   - Evaluated `add_to_cart_order` using the Interquartile Range method:
     $$\text{IQR} = Q_3 - Q_1, \quad \text{Upper Fence} = Q_3 + 1.5 \times \text{IQR}$$
   - Extreme outlier cart additions beyond the upper fence were capped (winsorized) to preserve ordinal ranking while preventing high-variance distortion in downstream linear/neural models.
5. **Inconsistent Format Normalization**:
   - Trimmed leading/trailing whitespaces and lowercased categorical string fields (`department`, `aisle`, `product_name`).
   - Enforced strict integer casting for primary/foreign keys and target flags.
6. **Persistence**: Exported verified cleaned data to [`data/processed/cleaned_instacart_data.csv`](data/processed/cleaned_instacart_data.csv).

---

## 4. Key Exploratory Findings & Insights

All exploratory analyses and visualizations are documented in [`notebooks/02_exploratory_data_analysis.ipynb`](notebooks/02_exploratory_data_analysis.ipynb) with standalone plots in [`results/figures/`](results/figures/):

| Visual Artifact | Key Distribution / Trend | Actionable Modeling Insight |
| :--- | :--- | :--- |
| **`01_target_class_distribution.png`** | Target `reordered` is **59.8% positive** and **40.2% negative**. | Moderate class imbalance. Accuracy is insufficient; models must optimize PR-AUC, F1-score, and calibrated probability thresholds. |
| **`02_orders_by_day_of_week.png`** | Strong demand spikes on **Sunday (day 0)** and **Monday (day 1)**; mid-week volume is flat. | Day-of-week is a strong cyclical predictor of user purchase intent and basket composition. |
| **`03_orders_by_hour_of_day.png`** | Pronounced diurnal curve surging at 08:00, peaking **10:00–16:00**, dropping after 20:00. | Diurnal patterns suggest grouping time into broad operational windows (morning, peak daytime, evening, night). |
| **`04_days_since_prior_order_distribution.png`** | Multimodal distribution with periodic spikes at **7, 14, 21, and 30 days**. | Users adhere to weekly/monthly grocery schedules. Modulo-7 cyclical day features capture replenishment cadence. |
| **`05_basket_size_distribution.png`** | Right-skewed distribution; median basket size is **8 items** (interquartile range 4 to 14). | Skewed counts require log transformations or non-parametric tree ensembles to prevent gradient blowup. |
| **`06_basket_size_boxplot_outliers.png`** | Reordered items have significantly lower median `add_to_cart_order` than first-time items. | **Cart Priority Effect**: Consumers add regular repeat staples into the basket first; late items are exploratory or impulse buys. |
| **`07_top_departments_and_reorder_rate.png`** | `produce` and `dairy eggs` constitute top volume with **reorder rates >65%**; `personal care` <35%. | Department category embeddings provide strong classification signal for baseline reorder probabilities. |
| **`08_correlation_heatmap.png`** | Negative correlation ($r \approx -0.15$) between `add_to_cart_order` and `reordered`; low collinearity among features ($|r| < 0.2$). | Clean feature space with low multicollinearity ensures stable model convergence without variance inflation. |

For detailed individual notes on each plot, see [`results/figures/README.md`](results/figures/README.md).

---

## 5. Feature Preprocessing & Scaling

Implemented and verified in [`notebooks/03_preprocessing_scaling.ipynb`](notebooks/03_preprocessing_scaling.ipynb):

1. **Cyclical Encodings**: Converted discrete temporal features (`order_dow` and `order_hour_of_day`) into continuous circular dimensions using sine and cosine coordinates ($\sin(\frac{2\pi \cdot t}{T})$, $\cos(\frac{2\pi \cdot t}{T})$).
2. **Relative Cart Position**: Created `cart_ratio = add_to_cart_order / basket_size` to capture normalized basket priority.
3. **Leakage-Free Stratified Split**: Partitioned data into 80% training ($N = 80,000$) and 20% test ($N = 20,000$) stratified on `reordered`.
4. **Comparative Scaling Evaluated**:
   - **`StandardScaler`**: Centers to $\mu=0, \sigma^2=1$.
   - **`MinMaxScaler`**: Bounded into $[0, 1]$.
   - **`RobustScaler`**: Scaled via median and IQR to neutralize residual tail effects.
5. **Empirical Baseline Validation**:
   - Logistic Regression trained on scaled features achieved an ROC-AUC of **0.672** with rapid parameter convergence.
6. **Export**: Processed feature matrix saved to [`data/processed/scaled_features.csv`](data/processed/scaled_features.csv).

---

## 6. How to Run the Notebooks

### Prerequisites
- Python 3.11+
- Git

### Installation
Clone the repository and install dependencies:
```powershell
git clone https://github.com/tayyab34996/SmartCart.git
cd SmartCart
pip install -r requirements.txt
```

### Running the Notebooks
Launch Jupyter Lab or Jupyter Notebook:
```powershell
jupyter notebook
```
Execute the notebooks in sequence:
1. `notebooks/01_data_cleaning.ipynb` — Ingests raw data, cleans missing values, deduplicates, winsorizes outliers, and writes `data/processed/cleaned_instacart_data.csv`.
2. `notebooks/02_exploratory_data_analysis.ipynb` — Generates distribution statistics, correlation matrices, and saves high-resolution figures to `results/figures/`.
3. `notebooks/03_preprocessing_scaling.ipynb` — Engineers cyclical features, evaluates comparative scalers, runs baseline classifier validation, and writes `data/processed/scaled_features.csv`.

Alternatively, reproduce all notebooks and figures headless via the automated build scripts:
```powershell
python scripts/build_cleaning.py
python scripts/build_eda.py
python scripts/build_preprocessing.py
```

### Running Unit & Integrity Tests
```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

---

## 7. Project Structure

```text
SmartCart/
|-- .gitignore                               # Configured to track figures, clean CSVs, and code
|-- LICENSE                                  # Open source license
|-- README.md                                # Comprehensive project documentation
|-- requirements.txt                         # Pinned Python package dependencies
|-- configs/                                 # Configuration manifests (data audits, experiments)
|   `-- data_audit.json
|-- data/
|   |-- raw/                                 # Raw ZIP archives (archive_3.zip, archive_4.zip)
|   |-- processed/                           # Cleaned and standardized data artifacts
|   |   |-- cleaned_instacart_data.csv       # Cleaned dataset (missing values & outliers handled)
|   |   |-- scaled_features.csv              # Standardized features ready for machine learning
|   |   `-- pilot/catalog.json               # Seed recipe-to-product mapping catalog
|   `-- interim/audit/                       # Audit summary and review shortlists
|-- docs/                                    # Extended architectural and data audit reports
|   |-- data_audit.md
|   |-- data_dictionary.md
|   `-- dataset_selection.md
|-- notebooks/                               # Executed Jupyter Notebooks (outputs visible)
|   |-- 01_data_cleaning.ipynb               # Data cleaning: missing values, duplicates, outliers
|   |-- 02_exploratory_data_analysis.ipynb   # Complete EDA with high-res visualizations
|   `-- 03_preprocessing_scaling.ipynb       # Cyclical encoding, feature scaling & normalization
|-- results/
|   `-- figures/                             # Generated high-resolution visualization plots
|       |-- 01_target_class_distribution.png
|       |-- 02_orders_by_day_of_week.png
|       |-- 03_orders_by_hour_of_day.png
|       |-- 04_days_since_prior_order_distribution.png
|       |-- 05_basket_size_distribution.png
|       |-- 06_basket_size_boxplot_outliers.png
|       |-- 07_top_departments_and_reorder_rate.png
|       |-- 08_correlation_heatmap.png
|       `-- README.md                        # Descriptive notes for each visualization
|-- scripts/                                 # Pipeline generation and verification scripts
|   |-- audit_data.py
|   |-- build_cleaning.py
|   |-- build_eda.py
|   |-- build_preprocessing.py
|   `-- validate_pilot.py
|-- src/smartcart/                           # Core modular source package
`-- tests/                                   # Unit and contract regression test suite
```
