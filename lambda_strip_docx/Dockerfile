FROM public.ecr.aws/lambda/python:3.13@sha256:f20766174b9dc98264b802947d9dda311f1f6c33413c12a479b795d1442e4668

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
