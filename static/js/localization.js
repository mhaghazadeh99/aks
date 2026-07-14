document.addEventListener(
    "DOMContentLoaded",
    function () {


        const language =
            document.documentElement.lang;


        if(language !== "fa"){
            return;
        }


        document
        .querySelectorAll(".datepicker")
        .forEach(function(input){


            input.type = "text";


            input.placeholder =
                "1405/01/01";


        });


    }
);