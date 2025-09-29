FROM public.ecr.aws/lambda/python:3.13@sha256:c9419beaca14fb851aca6f9432ec8fc0ad039eb0591df5c92e671ddd210fd2ac

# Install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Set the CMD to your handler (handler.lambda_handler)
CMD ["lambda_function.lambda_handler"]
