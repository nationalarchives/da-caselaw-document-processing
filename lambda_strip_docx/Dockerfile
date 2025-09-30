FROM public.ecr.aws/lambda/python:3.13@sha256:90256ba0b2d70eb29295cbfaddeab391b65214fe63fb20d4b8b6c25e22711629

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
