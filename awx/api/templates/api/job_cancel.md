{% ifmeth GET %}
# Determine if a Job can be canceled

Make a GET request to this resource to determine if the job can be canceled.
{% endifmeth %}

{% ifmeth POST %}
# Cancel a Job
Make a POST request to this resource to cancel a pending or running job.  The
response status code will be 202 if successful, or 405 if the job cannot be
canceled.
{% endifmeth %}
