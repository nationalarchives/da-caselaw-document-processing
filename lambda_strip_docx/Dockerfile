FROM public.ecr.aws/lambda/python:3.13

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
