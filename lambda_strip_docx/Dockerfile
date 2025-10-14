FROM public.ecr.aws/lambda/python:3.13@sha256:189046ab773d9246d47abeb8562d924e39fa6e829c823aefa2dc0aaa311e2565

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
