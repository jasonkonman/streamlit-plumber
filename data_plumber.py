from os import remove
import streamlit as st
import numpy as np
import pandas as pd
import xlrd
import re
import datetime
from collections import Counter

def main():

    ### Config lookup 
    config_lookup = {
        "saas": {
            "fields": ["first_name","last_name","patient_id","email","mobile","dob","gender","ethnicity","clinician_name","track_name","track_date"],
            "required_fields": ["patient_id","email","mobile"],
            "date_fields": ["dob","track_date"],
            "phone_fields": ["mobile"],
            "enum_fields": {
                "gender": ["Male", "Female"],
                "ethnicity": ["Sikh", "German", "New Zealand", "Australian", "Chinese", "Maori","Japanese", "English", "Irish", "Scottish", "Italian"]
            },
        },
    }
   
    country_code_lookup = {
        "sg": {"code": "65", "digits_ex": 8 },
        "nz": {"code": "64", "digits_ex": 8 },
        "au": {"code": "61", "digits_ex": 8 }
    }

    ### Title
    st.title("Patient Data Cleaner")

    ### Section 1: Upload source file
    with st.container() as container_1:
        st.header("Step 1: Upload File")
        with st.form(key='upload_xlsx'):
            input_file = st.file_uploader("Upload excel file here", type=['xls','xlsx','csv'], key='dirty_file')
            output_name = st.text_input(label='Output file name')
            active_country = st.selectbox("Select country", country_code_lookup.keys(), 0)
            submit_button = st.form_submit_button(label='Upload & Display')
    
    ### Setting config: can be done later after form
    active_config = "saas"
    # active_country = "sg"

    ### Set all fields based on active_config and config_lookup
    pre_fields = config_lookup[active_config]['fields']
    pre_required_fields = config_lookup[active_config]['required_fields']
    pre_date_fields = config_lookup[active_config]['date_fields']
    pre_phone_fields = config_lookup[active_config]['phone_fields']

    ### set active country settings
    country_config = country_code_lookup[active_country]

    ### data preprocessing function
    def output_dummy_data(df_input):
        return df_input
    
    def fix_excel_date(serial_date):
        """fix excel date with python datetime"""
        serial_int = int(serial_date)
        return datetime.datetime(1900, 1, 1) + datetime.timedelta(days=serial_int)
        
    def process_input_df(df_input):
        """Data preprocessing for dataframe to get uploadable csv"""
        df = df_input.copy()
        col_list = df.columns.to_list()

        ### Global vars for field lists
        global fields
        global required_fields
        global date_fields
        global phone_fields

        global not_fields
        global not_required_fields
        global not_date_fields
        global not_phone_fields

        global wrong_fields

        ### Fields that are present in df
        fields = [field for field in pre_fields if field in col_list]
        required_fields = [field for field in pre_required_fields if field in col_list]
        date_fields = [field for field in pre_date_fields if field in col_list]
        phone_fields = [field for field in pre_phone_fields if field in col_list]

        ### Fields that are absent in df
        not_fields = [field for field in pre_fields if field not in col_list]
        not_required_fields = [field for field in pre_required_fields if field not in col_list]
        not_date_fields = [field for field in pre_date_fields if field not in col_list]
        not_phone_fields = [field for field in pre_phone_fields if field not in col_list]

        ### Fields that shouldn't be there
        wrong_fields = [field for field in col_list if field not in pre_fields]

        # print(df.dtypes, "after wrong fields")

        ### Process date fields
        for date_field in date_fields:
            # print(f"date_field {df[date_field].dtype}")
            date_list = df[date_field].to_list()

            ### Fix Excel Fields
            new_list = []
            for item in date_list:
                if item and len(item) == 5:
                    new_list.append(fix_excel_date(item))
                else:
                    new_list.append(item)
            
            df[date_field] = new_list

            ### Convert to ISO-8601 format
            df[date_field] = pd.to_datetime(df[date_field])
            df[date_field] = df[date_field].dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        ### Process Gender Fields
        if 'gender' in fields:
            df.loc[df['gender'].str.lower().str.startswith("m"), 'gender'] = "Male"
            df.loc[df['gender'].str.lower().str.startswith("f"), 'gender'] = "Female"
        

        ### Format Ethnicity fields
        if 'ethnicity' in fields:
            df['ethnicity'] = df['ethnicity'].str.title()

        ### Initiate issues field
        df['upload_issues'] = None

        ### Process phone number fields
        for phone_field in phone_fields:
            ### change field to string
            df[phone_field] = df[phone_field].astype(str)
            ### strip non numbers
            df[phone_field] = df[phone_field].str.extract('(\d+)')
            # df.loc[df[phone_field].str.match("^\+.*", na=None), phone_field] = "+" + df[phone_field].str.extract('(\d+)')
            # df.loc[df[phone_field].str.match("^[0-9].*", na=None), phone_field] = df[phone_field].str.extract('(\d+)')

            ### name check fields
            check_field = phone_field + "_check"

            ### address those starting with "+", mark as clean
            # df.loc[df[phone_field].str.startswith("+"), check_field] = "clean"
            
            ### ignore everything starting with local country code, just add "+"
            df.loc[df[phone_field].str.startswith(country_config['code']), check_field] = "clean"
            df.loc[df[phone_field].str.startswith(country_config['code']), phone_field] = "+" + df[phone_field]

            ### for items starting with 0, remove zero, then add +countrycode
            df.loc[df[phone_field].str.startswith("0"), check_field] = "clean"
            df.loc[df[phone_field].str.startswith("0"), phone_field] = "+" + df[phone_field].str.lstrip("0")

            ### for items with same or less than optimal format, add local country code
            df.loc[df[phone_field].astype(str).map(len) <= country_config['digits_ex'] , check_field] = "ambiguous"
            df.loc[df[phone_field].astype(str).map(len) <= country_config['digits_ex'] , check_field] = "+" + country_config['code']  + df[phone_field]

            ### Highlight issues for malformed phone number
            df.loc[df[check_field].isin(['ambiguous']) | df[check_field].isnull(), 'upload_issues' ] = df['upload_issues'] + f", check {phone_field} field"        
        

        ### Highlight issues with required fields
        for required_field in required_fields:
            df.loc[df[required_field].isnull(), 'upload_issues' ] = df['upload_issues'] + f", {required_field} missing"
        
        ### Highlight gender issues
        if 'gender' in fields:
            df.loc[~df['gender'].isin(config_lookup['saas']['enum_fields']['gender']), 'upload_issues'] = df['upload_issues'] + ", check gender field"

        ### Highlight racial issues
        if 'ethnicity' in fields:
            df.loc[~df['ethnicity'].isin(config_lookup['saas']['enum_fields']['ethnicity']), 'upload_issues'] = df['upload_issues'] + ", check ethnicity field"

        # for field in not_fields:

        # print(df.dtypes, "before return")
        return(df)

    def add_missing_fields(df):
        """Add missing fields"""
        df = df.copy()
        for field in not_fields:
            df[field] = None
        
        return df

    def remove_wrong_fields(df):
        """remove wrong fields"""
        df = df.copy()
        df.drop(columns=wrong_fields, inplace=True)
        return df
        
    
    def fix_field_set(df):
        """Add missing fields, remove others"""
        df = df[fields].copy()

        for field in not_fields:
            df[field] = None
        
        return df

    def check_fields_missing_values(df, field_list):
        """check if required fields are null using a df and a reference field list. should only run after fix_field_set"""
        null_count = []
        for field in field_list:
            _dict = {}
            _dict[field] = df[df[field].isnull()][[field]].shape[0]
            null_count.append(_dict)
        
        both_dict = {}
        both_dict['all_contact_details'] = df[(df['mobile'].isnull()) & (df['mobile'].isnull())].shape[0]
        null_count.append(both_dict)
        
        return null_count


    def parse_dates(df):
        """Parse date fields and cast them to for upload"""
        for date_field in date_fields:
            df[date_field] = pd.to_datetime(df[date_field]).dt.strftime('%Y-%m-%dT%H:%M:%SZ')


    def output_csv(dataframe, has_header=True): 
        """Takes a dataframe and has header argument to produce csv file to buffer for download button to use"""
        return dataframe.to_csv(sep=",", index=False, header=has_header).encode('utf-8')

    def download_success():
        """Success message on download"""
        st.success("Download Successful!")


    ### Checking if file is valid
    if submit_button:
        try:
            st.success(f"{input_file.name} has been selected\n\n")
            st.header("\n\nStep 2: Check Data")
            if input_file is None:
                pass
            elif input_file.name.endswith('.csv'):
                input_df = pd.read_csv(input_file)
            else:
                input_df = pd.read_excel(input_file, dtype=str, parse_dates=False)
            
    ### Display input_df
            with st.container():
                st.subheader("Input Data")
                input_df

    ### Preprocess data
            processed_df = process_input_df(input_df)
            # print(processed_df.dtypes, "processed")

    ### OUTPUT df container
            container_output = st.container()
            container_output.subheader("Output Data")
            # container_output.write(processed_df)
            

    ### Highlight: Missing Fields
            st.header("Step 3: Fix Issues")
            st.subheader("Missing/ incorrectly named columns")
            missing_df = pd.DataFrame(columns=['missing_field', 'required'])
            for field in not_fields:
                if field in pre_required_fields:
                    missing_df = missing_df.append({'missing_field': field, 'required': 'Required'}, ignore_index=True)
                else:
                    missing_df = missing_df.append({'missing_field': field, 'required': ""}, ignore_index=True)
            missing_df

    ### Add missing fields
            full_df_with_wrong_fields = add_missing_fields(processed_df)
            # print(full_df_with_wrong_fields.dtypes, "full df with wrong fields")
    
    ### Remove wrong fields
            output_df = remove_wrong_fields(full_df_with_wrong_fields)
            print(output_df.dtypes, "before order")
            output_df_display_order = ['upload_issues'] + pre_fields
            output_df = output_df[output_df_display_order] 
            print(output_df.dtypes, "after order")
            container_output.write(output_df)
            # print(wrong_fields)

    ### Highlight: Issues with Required fields
            required_null = check_fields_missing_values(output_df, required_fields)
            st.subheader("Issues with required fields")
            for i in required_null:
                for k,v in i.items():
                    st.markdown(f"**{k}:** {v} missing records")
            
    ### Highlight: All issues
            st.subheader("Frequency of issues")
            issue_list = output_df['upload_issues'].str.cat(sep=', ').split(', ')
            issue_dict = Counter(issue_list)
            

            for k,v in issue_dict.items():
                if k == "":
                    st.write(f"No Issues")
                else:
                    st.write(f"{k}: {v} times")


    ### [Missing] Output of csv files    
            if output_df is not None:

                clean_df = output_df[pre_fields].copy()

                out_csv = output_csv(output_df, True)
                out_csv_noheader = output_csv(clean_df, False)

                csv_path = output_name + ".csv"
                csv_path_noheader = output_name + "_for_upload.csv"

                st.header("\n\nStep 4: Download CSV")
                st.download_button(
                    label = "Download CSV (with headers)",
                    data=out_csv,
                    file_name=csv_path,
                    mime='text/csv',
                    on_click=download_success)

                st.download_button(
                    label = "Download CSV (no headers)",
                    data = out_csv_noheader,
                    file_name = csv_path_noheader,
                    mime='text/csv', 
                    on_click=download_success)
                
        
        except AttributeError:
            st.error("Please select a file before continuing")


if __name__ == '__main__':
    main()