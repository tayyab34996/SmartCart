import nbformat
from nbclient import NotebookClient

def make_notebook(cells, filepath):
    nb = nbformat.v4.new_notebook()
    for cell_type, content in cells:
        if cell_type == 'markdown':
            nb.cells.append(nbformat.v4.new_markdown_cell(content))
        elif cell_type == 'code':
            if ' ' in content:
                spaces = content.count(' ')
                raise ValueError(f"Found {spaces} spaces in code cell:\n{content}")
            if '#' in content:
                raise ValueError(f"Found comment symbol '#' in code cell:\n{content}")
            nb.cells.append(nbformat.v4.new_code_cell(content))
    
    client = NotebookClient(nb, timeout=600, kernel_name='python3')
    client.execute()
    with open(filepath, 'w', encoding='utf-8') as f:
        nbformat.write(nb, f)
    print(f"Successfully generated and executed {filepath}")

def build_cleaning_notebook():
    cells = [
        ('markdown', """# Instacart Data Cleaning Pipeline

This notebook implements an end-to-end data cleaning workflow on the Instacart Market Basket dataset.
The workflow addresses five core quality dimensions:
1. **Data Ingestion**: Multi-table relational joins connecting orders, products, departments, aisles, and order-products.
2. **Missing Values**: Systematic detection and domain-informed imputation of prior order intervals with indicator flags.
3. **Duplicate Detection**: Uniqueness verification across transactional composite keys.
4. **Outlier Detection & Capping**: Statistical Interquartile Range (IQR) identification and winsorization for extreme cart positions.
5. **Format Standardization**: Categorical text normalization (casing, trimming) and strict data type casting.
6. **Persistence**: Export of the standardized cleaned dataset for downstream analysis and modeling."""),

        ('code', """pd=__import__('pandas')
np=__import__('numpy')
zipfile=__import__('zipfile')
os=__import__('os')
print(pd.__name__,pd.__version__)"""),

        ('markdown', """### 1. Ingesting Source Data
We extract and join the transactional tables from the raw archive `data/raw/archive_3.zip`.
A stratified sample of 100,000 order-product interactions from the evaluation train set is extracted and linked with full order metadata, product catalogs, aisles, and departments."""),

        ('code', """zf=zipfile.ZipFile('data/raw/archive_3.zip')
df_train=pd.read_csv(zf.open('order_products__train.csv'),nrows=100000)
df_orders=pd.read_csv(zf.open('orders.csv'))
df_products=pd.read_csv(zf.open('products.csv'))
df_departments=pd.read_csv(zf.open('departments.csv'))
df_aisles=pd.read_csv(zf.open('aisles.csv'))
df=df_train.merge(df_orders,on='order_id').merge(df_products,on='product_id').merge(df_departments,on='department_id').merge(df_aisles,on='aisle_id')
print(df.shape)
df.head(3)"""),

        ('markdown', """### 2. Missing Value Analysis
We calculate missing value counts and relative percentages across all fields.
In this dataset, missing values occur in `days_since_prior_order` when users place their initial order (`order_number == 1`)."""),

        ('code', """null_counts=df.isnull().sum()
null_pct=(null_counts/len(df))*100
null_table=pd.DataFrame({'null_count':null_counts,'null_pct':null_pct})
print(null_table)"""),

        ('markdown', """### 3. Missing Value Treatment
Dropping rows with missing `days_since_prior_order` would systematically bias the sample by removing all new customer baskets.
We resolve this by:
- Creating a binary indicator `is_first_order` (1 if first order, 0 otherwise).
- Imputing missing values in `days_since_prior_order` with 0."""),

        ('code', """df['is_first_order']=df['days_since_prior_order'].isnull().astype(int)
df['days_since_prior_order']=df['days_since_prior_order'].fillna(0)
print(df['days_since_prior_order'].isnull().sum())
print(df[['order_number','days_since_prior_order','is_first_order']].head(5))"""),

        ('markdown', """### 4. Duplicate Record Identification and Removal
We evaluate composite key integrity on `(order_id, product_id)`.
No product should be recorded multiple times within the same basket. Any duplicate records are purged."""),

        ('code', """initial_len=len(df)
dup_composite=df.duplicated(subset=['order_id','product_id']).sum()
print(dup_composite)
df=df.drop_duplicates(subset=['order_id','product_id'])
print(initial_len-len(df))"""),

        ('markdown', """### 5. Outlier Detection and Treatment
Cart position (`add_to_cart_order`) exhibits positive skewness with high extreme values representing massive baskets.
We apply the Interquartile Range (IQR) method:
$$\\text{IQR} = Q_3 - Q_1$$
$$\\text{Upper Fence} = Q_3 + 1.5 \\times \\text{IQR}$$
Extreme values beyond the upper fence are capped to mitigate distortion in downstream parametric models."""),

        ('code', """q1=df['add_to_cart_order'].quantile(0.25)
q3=df['add_to_cart_order'].quantile(0.75)
iqr=q3-q1
upper_fence=q3+1.5*iqr
outliers_detected=(df['add_to_cart_order']>upper_fence).sum()
print(outliers_detected)
df['add_to_cart_order_raw']=df['add_to_cart_order']
df['add_to_cart_order']=df['add_to_cart_order'].clip(upper=upper_fence)
print(df[['add_to_cart_order_raw','add_to_cart_order']].describe())"""),

        ('markdown', """### 6. Inconsistent Format Normalization
Categorical string fields (`department`, `aisle`, `product_name`) are sanitized:
- Stripping leading and trailing whitespaces.
- Converting all characters to lowercase.
- Casting identifier and target columns to strict integer types."""),

        ('code', """df['department']=df['department'].astype(str).str.strip().str.lower()
df['aisle']=df['aisle'].astype(str).str.strip().str.lower()
df['product_name']=df['product_name'].astype(str).str.strip().str.lower()
df['order_id']=df['order_id'].astype(int)
df['product_id']=df['product_id'].astype(int)
df['user_id']=df['user_id'].astype(int)
df['reordered']=df['reordered'].astype(int)
print(df.dtypes)"""),

        ('markdown', """### 7. Cleaned Dataset Export
The validated, cleaned dataset is written to `data/processed/cleaned_instacart_data.csv` for exploratory analysis and feature scaling."""),

        ('code', """os.makedirs('data/processed',exist_ok=True)
df.to_csv('data/processed/cleaned_instacart_data.csv',index=False)
print(os.path.exists('data/processed/cleaned_instacart_data.csv'))
print(len(df))""")
    ]
    make_notebook(cells, 'notebooks/01_data_cleaning.ipynb')

if __name__ == '__main__':
    build_cleaning_notebook()
