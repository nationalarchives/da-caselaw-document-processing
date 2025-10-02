FROM public.ecr.aws/lambda/python:3.13@sha256:de368792d89827e950d750704b6b5c4505d5462b033881d2916997781c9b241d

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
