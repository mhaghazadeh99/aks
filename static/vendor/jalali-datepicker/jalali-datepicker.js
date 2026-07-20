document.addEventListener(
"DOMContentLoaded",
function(){


const datepickers =
document.querySelectorAll(".datepicker");


if(!datepickers.length){
    return;
}


let activeDatepicker = null;



const calendarContainer =
document.createElement("div");


calendarContainer.id =
"calendar-container";


calendarContainer.className =
"calendar-container";


document.body.appendChild(
    calendarContainer
);



function positionCalendar(input){

    const rect =
    input.getBoundingClientRect();


    calendarContainer.style.position =
        "absolute";


    calendarContainer.style.top =
        window.scrollY +
        rect.bottom +
        "px";


    calendarContainer.style.left =
        window.scrollX +
        rect.left +
        "px";

}




calendarContainer.innerHTML = `

<div class="calendar">

<div class="calendar-header">

<button id="prev-month">
قبلی
</button>


<span id="calendar-title"></span>


<button id="next-month">
بعدی
</button>


</div>


<div class="calendar-body"></div>


</div>

`;



const calendar =
calendarContainer.querySelector(
".calendar"
);


const calendarTitle =
document.getElementById(
"calendar-title"
);


const prevMonthButton =
document.getElementById(
"prev-month"
);


const nextMonthButton =
document.getElementById(
"next-month"
);



const jalaaliMonths = [

"فروردین",
"اردیبهشت",
"خرداد",
"تیر",
"مرداد",
"شهریور",
"مهر",
"آبان",
"آذر",
"دی",
"بهمن",
"اسفند"

];



let currentDate =
new Date();



let currentLanguage =
document.documentElement.lang === "fa"
?
"fa"
:
"en";


function updateCalendar(){

    if(currentLanguage === "fa"){
        updateJalaliCalendar();
    }else{
        updateGregorianCalendar();
    }

}



function updateJalaliCalendar(){


if(typeof jalaali === "undefined"){

console.error(
"jalaali.js not loaded"
);

return;

}



const jdate =
jalaali.toJalaali(

currentDate.getFullYear(),

currentDate.getMonth()+1,

1

);
prevMonthButton.textContent = "قبلی";
nextMonthButton.textContent = "بعدی";


const monthDays =
jalaali.jalaaliMonthLength(

jdate.jy,

jdate.jm

);



calendarTitle.innerHTML =

`${jdate.jy} ${jalaaliMonths[jdate.jm-1]}`;



calendar.querySelector(
".calendar-body"
).innerHTML =



Array.from(
{length:monthDays},
(_,i)=>


`

<div class="day">
${i+1}
</div>

`

).join("");





calendar
.querySelectorAll(".day")
.forEach(function(day){


day.addEventListener(
"click",
function(){


const selectedDay =
Number(this.textContent);




if(currentLanguage==="fa"){



activeDatepicker.value =

`${jdate.jy}/${String(jdate.jm).padStart(2,"0")}/${String(selectedDay).padStart(2,"0")}`;



const gregorian =

jalaali.toGregorian(

jdate.jy,

jdate.jm,

selectedDay

);



activeDatepicker.dataset.gregorian =

`${gregorian.gy}-${String(gregorian.gm).padStart(2,"0")}-${String(gregorian.gd).padStart(2,"0")}`;

console.log(
    "Gregorian:",
    activeDatepicker.name,
    activeDatepicker.dataset.gregorian
);

}

else{


activeDatepicker.value =

`${currentDate.getFullYear()}-${String(currentDate.getMonth()+1).padStart(2,"0")}-${String(selectedDay).padStart(2,"0")}`;


activeDatepicker.dataset.gregorian =

activeDatepicker.value;


}



calendarContainer.style.display =
"none";



});


});


}



function updateGregorianCalendar(){

    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    const monthNames = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December"
    ];

    calendarTitle.innerHTML =
        `${monthNames[month]} ${year}`;

    prevMonthButton.textContent = "Previous";
    nextMonthButton.textContent = "Next";

    const monthDays =
        new Date(year, month + 1, 0).getDate();

    calendar.querySelector(".calendar-body").innerHTML =
        Array.from(
            {length: monthDays},
            (_, i) =>
            `
            <div class="day">
                ${i + 1}
            </div>
            `
        ).join("");

    calendar
        .querySelectorAll(".day")
        .forEach(function(day){

            day.addEventListener(
                "click",
                function(){

                    const selectedDay =
                        Number(this.textContent);

                    activeDatepicker.value =
                        `${year}-${String(month+1).padStart(2,"0")}-${String(selectedDay).padStart(2,"0")}`;

                    activeDatepicker.dataset.gregorian =
                        activeDatepicker.value;

                    calendarContainer.style.display =
                        "none";

                }
            );

        });

}



datepickers.forEach(
function(input){


input.addEventListener(
"click",
function(e){


e.preventDefault();


activeDatepicker =
this;


positionCalendar(this);



calendarContainer.style.display =
"block";


updateCalendar();


});


});





document.addEventListener(
"click",
function(event){


let insideInput=false;



datepickers.forEach(
function(input){


if(input.contains(event.target)){

insideInput=true;

}


});



if(
!calendarContainer.contains(event.target)
&&
!insideInput
){

calendarContainer.style.display =
"none";

}


});





prevMonthButton.addEventListener(
"click",
function(){

currentDate.setMonth(
currentDate.getMonth()-1
);


updateCalendar();


});




nextMonthButton.addEventListener(
"click",
function(){

currentDate.setMonth(
currentDate.getMonth()+1
);


updateCalendar();


});





/*
Convert Jalali display
to Gregorian before submit
*/

document.querySelectorAll("form").forEach(function(form){

    form.addEventListener("submit", function(){

        console.log("FORM SUBMITTED");

        form.querySelectorAll(".datepicker").forEach(function(input){

            console.log(
                input.name,
                "before:",
                input.value,
                "->",
                input.dataset.gregorian
            );

            if(input.dataset.gregorian){

                input.value = input.dataset.gregorian;

            }

            console.log(
                input.name,
                "after:",
                input.value
            );

        });

    });

});

updateCalendar();



});

