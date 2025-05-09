import streamlit as st
import pandas as pd
import tabula
import camelot
import tempfile
import os
import io
from typing import List, Dict
import pdfplumber
import re

def extract_header_with_camelot(pdf_path: str) -> dict:
    """Extract header fields using Camelot with precise PO number location."""
    header_data = {
        "invoice_number": "INV-XXXXXX",
        "invoice_date": None,
        "po_number": None
    }
    
    try:
        # Use Camelot to extract all tables from first page
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')
        
        # Get PO Number from specific location (4th table, 2nd row, 2nd column)
        if len(tables) >= 4:
            table_4 = tables[3].df  # 4th table (0-indexed as 3)
            if len(table_4) >= 2 and len(table_4.columns) >= 2:
                po_cell = str(table_4.iloc[1, 1])  # 2nd row, 2nd column
                # Extract 10-digit PO number
                po_match = re.search(r'\d{10}', po_cell)
                if po_match:
                    header_data["po_number"] = po_match.group()
        
        # Get Invoice Number and Date from other tables
        for table in tables:
            df = table.df
            for i in range(min(5, len(df))):  # Check first 5 rows
                row = df.iloc[i].str.lower()
                
                # Invoice Number (format: 3378472-00)
                if 'invoice' in row.str.cat() and 'date' not in row.str.cat():
                    for cell in df.iloc[i]:
                        if re.search(r'\d{7}-\d{2}', str(cell)):
                            header_data["invoice_number"] = re.search(r'\d{7}-\d{2}', str(cell)).group()
                            break
                
                # Invoice Date (format: 1/12/24)
                if 'invoice date' in row.str.cat():
                    for cell in df.iloc[i+1] if i+1 < len(df) else []:
                        if re.search(r'\d{1,2}/\d{1,2}/\d{2}', str(cell)):
                            header_data["invoice_date"] = re.search(r'\d{1,2}/\d{1,2}/\d{2}', str(cell)).group()
                            break
                    
    except Exception as e:
        st.warning(f"Camelot header extraction warning: {str(e)}")
    
    return header_data

def extract_invoice_data(pdf_path: str) -> List[Dict]:
    """Extract invoice data with precise PO number location."""
    try:
        # Get header data using Camelot
        header = extract_header_with_camelot(pdf_path)
        
        # Get product data using Tabula
        tables = tabula.read_pdf(
            pdf_path,
            pages='all',
            multiple_tables=True,
            lattice=True,
            pandas_options={'header': None}
        )
    except Exception as e:
        st.warning(f"Error processing PDF: {str(e)}")
        return []

    invoice_data = []
    filename = os.path.basename(pdf_path)
    
    # Search for product table
    for table in tables:
        if table.empty or len(table.columns) < 5:
            continue
            
        for _, row in table.iterrows():
            if len(row) > 0 and str(row[0]).strip().isdigit():
                product_code = str(row[1]).strip() if pd.notna(row[1]) else ""
                if not product_code:
                    continue
                
                description = "Auto Serpentine Belt"
                ship_qty = "0"
                for col in [4, 3, 5, 2]:  # Check quantity columns
                    if len(row) > col and pd.notna(row[col]):
                        qty = str(row[col]).strip()
                        if qty.isdigit():
                            ship_qty = qty
                            break
                
                invoice_data.append({
                    "INVOICE": header["invoice_number"],
                    "INVOICE DATE": header["invoice_date"] or "",
                    "PO#": header["po_number"] or "",
                    "Product & Description": f"{product_code} - {description}",
                    "Ship Qty": ship_qty,
                    "Source File": filename
                })
    
    return invoice_data

def process_multiple_pdfs(uploaded_files: List) -> pd.DataFrame:
    """Process multiple PDF files with progress tracking."""
    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, uploaded_file in enumerate(uploaded_files):
        try:
            status_text.text(f"Processing {i+1}/{len(uploaded_files)}: {uploaded_file.name}...")
            progress_bar.progress((i + 1) / len(uploaded_files))
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
            
            file_data = extract_invoice_data(tmp_path)
            all_data.extend(file_data)
            
        except Exception as e:
            st.warning(f"Error processing {uploaded_file.name}: {str(e)}")
        finally:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    return pd.DataFrame(all_data) if all_data else pd.DataFrame()

def main():
    st.title("Bando Invoice Batch Extractor")
    st.write("Upload multiple Bando invoice PDFs to extract data")
    
    uploaded_files = st.file_uploader(
        "Choose PDF files", 
        type="pdf",
        accept_multiple_files=True
    )
    
    if uploaded_files:
        with st.spinner("Processing files..."):
            df = process_multiple_pdfs(uploaded_files)
            
            if not df.empty:
                st.success(f"✅ Processed {len(uploaded_files)} file(s) with {len(df)} line items")
                
                st.subheader("Summary")
                cols = st.columns(3)
                cols[0].metric("Files Processed", len(uploaded_files))
                cols[1].metric("Total Items", len(df))
                cols[2].metric("Total Quantity", df['Ship Qty'].astype(int).sum())
                
                st.subheader("Extracted Data")
                st.dataframe(df)
                
                st.subheader("Export Data")
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "Download as CSV",
                    data=csv,
                    file_name="bando_invoices.csv",
                    mime="text/csv"
                )
                
                try:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    st.download_button(
                        "Download as Excel",
                        data=excel_buffer.getvalue(),
                        file_name="bando_invoices.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except ImportError:
                    st.warning("Excel export requires openpyxl. Install with: pip install openpyxl")
                
            else:
                st.error("No invoice data found. Check PDF formats.")

if __name__ == "__main__":
    main()