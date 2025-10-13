FROM public.ecr.aws/lambda/python:3.13@sha256:2d7fa165a150ac899101a61b0fbe1406929a587a13e5a7857a8a9bb0e2ce0782

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
