from .models import AttachmentType, OperationType


REQUIRED_DOCUMENTS = {


    OperationType.ISSUE_LICENCE: [

        AttachmentType.LETTER,

        AttachmentType.COMMITMENT,

        AttachmentType.REGULATORY_PERMIT,

        AttachmentType.SOURCE_INQUIRY,

    ],


    OperationType.RECEIVE_SOURCE: [

        AttachmentType.LETTER,

        AttachmentType.SOURCE_INQUIRY,

    ],


    OperationType.RECEIVE_WASTE: [

        AttachmentType.LETTER,

    ],


    OperationType.SELL_SOURCE: [

        AttachmentType.LETTER,

    ],

}