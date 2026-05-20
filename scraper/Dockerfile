FROM public.ecr.aws/lambda/python:3.11

RUN python -m pip install --upgrade pip
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --prefer-binary -r requirements.txt --no-cache-dir

# # Copy requirements file
# COPY requirements.txt ${LAMBDA_TASK_ROOT}

# # Install dependencies
# RUN pip install -r requirements.txt

# Pre-download NLTK data during container build - download both old and new punkt resources
RUN python -c "import nltk; import os; os.makedirs('/nltk_data', exist_ok=True); nltk.download('punkt', download_dir='/nltk_data'); nltk.download('punkt_tab', download_dir='/nltk_data')" || true

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set NLTK_DATA environment variable
ENV NLTK_DATA=/nltk_data

# Set the CMD to your handler
CMD [ "scrape_all.lambda_handler" ]