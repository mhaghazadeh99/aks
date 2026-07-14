document.addEventListener("DOMContentLoaded", function(){

    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");
    const toggleBtn = document.getElementById("toggleSidebar");


    function toggleSidebar(){

        sidebar.classList.toggle("open");
        overlay.classList.toggle("show");

    }


    toggleBtn.addEventListener(
        "click",
        toggleSidebar
    );


    overlay.addEventListener(
        "click",
        toggleSidebar
    );


});

const languageButton =
document.getElementById("languageButton");

const languageMenu =
document.getElementById("languageMenu");

if(languageButton){

languageButton.onclick=function(){

languageMenu.classList.toggle("show");

};

}