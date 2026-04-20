try:
    import jq
    JQ_AVAILABLE = True
except ImportError:
    JQ_AVAILABLE = False

from logger import log

class JSONLogicArchitect:
    """
    Expert bridge between complex raw JSON and human-readable results.
    Implements a strict ETL mindset for data transformation.
    """

    @staticmethod
    def search_json(data, jq_filter):
        """
        Safely executes a jq filter on a Python object.
        """
        if not JQ_AVAILABLE:
            err_msg = "JQ Engine not installed. Please try: pip install jq"
            log.error(err_msg)
            return {"error": err_msg}

        try:
            # The 'jq' package uses a compile/input/all flow
            # This is more modern and efficient than pyjq
            program = jq.compile(jq_filter)
            results = program.input(data).all()
            log.info(f"JQ Extraction successful. Matches found: {len(results)}")
            return results
        except Exception as e:
            err_msg = f"Syntax Error in JQ Filter: {str(e)}"
            log.error(err_msg)
            return {"error": err_msg}

    @staticmethod
    def construct_filter(scenario):
        """
        Utility to map common natural language requirements to JQ strings.
        This serves as a lookup for the 'Full Content' of implementation logic.
        """
        scenarios = {
            "mule_admin_orgs": '.user.memberOfOrganizations[] | select(.roles[] == "Organization Administrator") | .name',
            "status_started": '.[] | select(.status == "STARTED")',
            "correlation_match": '.logRetrieveResponse.result[] | select(.correlationId == $cid)',
            "error_suppression_base": '.items[]?.id'
        }
        return scenarios.get(scenario, ".")
